from random import getrandbits, choice
from base64 import urlsafe_b64encode
from datetime import date, datetime, timedelta
from contextlib import contextmanager
from typing import Type, Optional, Generator, Dict, Tuple

import psycopg2.extensions
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool

import pygments
import pygments.util
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, get_all_lexers
from pygments.formatters import HtmlFormatter

from flask.app import Flask
from flask.templating import render_template
from flask.helpers import url_for, flash, get_flashed_messages, make_response
from flask.globals import request
from flask.wrappers import Response

from werkzeug.exceptions import abort
from werkzeug.utils import redirect

from stats import pasteview, pastecount, getstats
from config import *
from config import url_len as url_len_map


app = Flask(__name__)
app.secret_key = secret_key
app.config["MAX_CONTENT_LENGTH"] = max_content_length
app.jinja_env.globals["year"] = date.today().year


connpool = SimpleConnectionPool(connpool_min, connpool_max, dsn)


@contextmanager
def getcursor(
    cursor_factory: Optional[Type[psycopg2.extensions.cursor]] = None,
) -> Generator:
    con = connpool.getconn()
    try:
        if cursor_factory:
            cursor = con.cursor(cursor_factory=cursor_factory)
        else:
            cursor = con.cursor()
        yield cursor
        con.commit()
    finally:
        connpool.putconn(con)


def plain(text: str) -> Response:
    resp = Response(text)
    resp.headers["Context-Type"] = "text/plain; charset=utf-8"
    return resp


def set_cache_control(resp: Response, max_age: int = 69) -> Response:
    resp.cache_control.public = True
    resp.cache_control.max_age = int(max_age)
    return resp


def paste_stats(text: str) -> Dict:
    stats = {}
    stats["lines"] = len(text.split("\n"))
    stats["sloc"] = stats["lines"]
    for line in text.split("\n"):
        if not line.strip():
            stats["sloc"] -= 1
    stats["size"] = len(text.encode("utf-8"))
    return stats


def url_collision(cursor: psycopg2.extensions.cursor, route: str) -> bool:
    for rule in app.url_map.iter_rules():
        if rule.rule == "/" + route:
            return True
    with cursor as cur:
        cur.execute("SELECT pasteid FROM pastes WHERE pasteid = %s;", (route,))
        if cur.fetchone():
            return True
    return False


def db_newpaste(
    cursor: psycopg2.extensions.cursor, opt: Dict[str, str], stats: Dict[str, int]
) -> None:
    date = datetime.utcnow()
    date += timedelta(hours=float(opt["ttl"]))
    with cursor as cur:
        cur.execute(
            """
            INSERT INTO
			pastes (pasteid, token, lexer, expiration, burn,
			paste, paste_lexed, size, lines, sloc)
			VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                opt["pasteid"],
                opt["token"],
                opt["lexer"],
                date,
                opt["burn"],
                opt["paste"],
                opt["paste_lexed"],
                stats["size"],
                stats["lines"],
                stats["sloc"],
            ),
        )


def db_getpaste(cursor: psycopg2.extensions.cursor, pasteid: int) -> Optional[Tuple]:
    with cursor as cur:
        cur.execute(("""SELECT * FROM pastes WHERE pasteid = %s;"""), (pasteid,))
    return cur.fetchone()


def db_deletepaste(cursor: psycopg2.extensions.cursor, pasteid: int) -> None:
    with cursor as cur:
        cur.execute(("""DELETE FROM pastes WHERE pasteid = %s;"""), (pasteid,))


def db_burn(cursor: psycopg2.extensions.cursor, pasteid: int) -> None:
    with cursor as cur:
        cur.execute(
            ("""UPDATE pastes SET burn = burn - 1 WHERE pasteid = %s;"""), (pasteid,)
        )


@app.route("/", methods=["GET", "POST"])
@app.route("/newpaste", methods=["POST"])
def newpaste():
    if request.method == "POST":
        paste_opt = {}
        for param in defaults:
            paste_opt[param] = defaults[param]
        for param in request.form:
            if param in paste_opt:
                paste_opt[param] = request.form[param]
        if paste_opt["paste"] == "":
            return msg_empty_paste, 400
        try:
            if (
                not paste_limits["ttl_min"]
                < float(paste_opt["ttl"])
                < paste_limits["ttl_max"]
            ):
                return msg_invalid_ttl, 400
        except ValueError:
            return msg_invalid_ttl, 400
        lexer = ""
        try:
            if paste_opt["lexer"] == "auto":
                lexer = guess_lexer(paste_opt["paste"])
                paste_opt["lexer"] = lexer.aliases[0]  # type: ignore
            else:
                lexer = get_lexer_by_name(paste_opt["lexer"])
        except pygments.util.ClassNotFound:
            paste_opt["lexer"] = "text"
            lexer = get_lexer_by_name(paste_opt["lexer"])

        formatter = HtmlFormatter(nowrap=True, cssclass="paste")
        paste_opt["paste_lexed"] = highlight(paste_opt["paste"], lexer, formatter)

        try:
            if (
                paste_opt["burn"] == ""
                or paste_opt["burn"] == 0
                or paste_opt["burn"] == defaults["burn"]
            ):
                paste_opt["burn"] = defaults["burn"]
            elif (
                not paste_limits["burn_min"]
                <= int(paste_opt["burn"])
                <= paste_limits["burn_max"]
            ):
                return msg_invalid_burn, 400
        except ValueError:
            return msg_invalid_burn, 400

        url_len = url_len_map
        paste_opt["pasteid"] = ""
        while url_collision(getcursor(), paste_opt["pasteid"]):  # type: ignore
            paste_opt["pasteid"] = ""
            for _ in range(url_len):
                paste_opt["pasteid"] += choice(url_alph)
            url_len += 1

        paste_opt["token"] = urlsafe_b64encode(
            (getrandbits(token_len * 8)).to_bytes(token_len, "little")
        ).decode("utf-8")

        stats = paste_stats(paste_opt["paste"])

        db_newpaste(getcursor(), paste_opt, stats)  # type: ignore

        pastecount(getcursor())  # type: ignore

        if request.path != "/newpaste":
            if paste_opt["raw"] == "true":
                reptype = "viewraw"
            else:
                reptype = "viewpaste"
            return (
                domain
                + url_for(reptype, pasteid=paste_opt["pasteid"])
                + " | "
                + paste_opt["token"]
                + "\n"
            )

        flash(paste_opt["token"])
        return redirect(paste_opt["pasteid"])
    elif request.method == "GET":
        lexers_all = sorted(get_all_lexers())
        return set_cache_control(
            make_response(
                render_template(
                    "newpaste.html",
                    lexers_all=lexers_all,
                    lexers_common=lexers_common,
                    ttl=ttl_options,
                    paste_limits=paste_limits,
                )
            ),
            nonpaste_max_age,
        )


@app.route("/<pasteid>", methods=["GET", "DELETE"])
def viewpaste(pasteid):
    if request.method == "GET":
        direction = "ltr"
        result = db_getpaste(getcursor(cursor_factory=DictCursor), pasteid)  # type: ignore
        if not result:
            abort(404)
        if result["burn"] == 0 or result["expiration"] < datetime.utcnow():  # type: ignore
            db_deletepaste(getcursor(), pasteid)  # type: ignore
            abort(404)
        elif result["burn"] > 0:  # type: ignore
            db_burn(getcursor(), pasteid)  # type: ignore

        pasteview(getcursor())  # type: ignore

        if request.args.get("raw") is not None:
            return set_cache_control(plain(result["paste"]), config.paste_max_age)  # type: ignore

        if request.args.get("d") is not None:
            direction = "rtl"

        stats = {
            "lines": result["lines"],  # type: ignore
            "sloc": result["sloc"],  # type: ignore
            "size": result["size"],  # type: ignore
            "lexer": result["lexer"],  # type: ignore
        }
        messages = get_flashed_messages()
        if messages:
            token = messages[0]
        else:
            token = ""

        del_url = url_for("deletepaste", pasteid=pasteid, token=token)
        resp = make_response(
            render_template(
                "viewpaste.html",
                stats=stats,
                paste=result["paste_lexed"].split("\n"),  # type: ignore
                direction=direction,
                delete=del_url,
            )
        )
        return set_cache_control(resp, paste_max_age)  # type: ignore

    elif request.method == "DELETE":
        result = db_getpaste(getcursor(cursor_factory=DictCursor), pasteid)  # type: ignore
        if not result:
            return msg_err_404, 404
        elif "token" in request.form and result["token"] == request.form["token"]:  # type: ignore
            db_deletepaste(getcursor(), pasteid)  # type: ignore
            return msg_paste_deleted, 200
        elif "token" in request.headers and result["token"] == request.headers.get(  # type: ignore
            "token"
        ):
            db_deletepaste(getcursor(), pasteid)  # type: ignore
            return msg_paste_deleted, 200
        else:
            return msg_err_401, 401


@app.route("/plain/<pasteid>", methods=["GET", "DELETE"])
@app.route("/raw/<pasteid>", methods=["GET", "DELETE"])
def viewraw(pasteid):
    if request.method == "GET":
        result = db_getpaste(getcursor(cursor_factory=DictCursor), pasteid)  # type: ignore
        if not result:
            return msg_err_404, 404
        if result["burn"] == 0 or result["expiration"] < datetime.utcnow():  # type: ignore
            db_deletepaste(getcursor(), pasteid)  # type: ignore
            return msg_err_404, 404
        elif result["burn"] > 0:  # type: ignore
            db_burn(getcursor(), pasteid)  # type: ignore

        pasteview(getcursor())  # type: ignore

        return set_cache_control(plain(result["paste"]), config.paste_max_age)  # type: ignore

    elif request.method == "DELETE":
        result = db_getpaste(getcursor(cursor_factory=DictCursor), pasteid)  # type: ignore
        if not result:
            return msg_err_404, 404
        elif "token" in request.form and result["token"] == request.form["token"]:  # type: ignore
            db_deletepaste(getcursor(), pasteid)  # type: ignore
            return msg_paste_deleted, 200
        elif "token" in request.headers and result["token"] == request.headers.get(  # type: ignore
            "token"
        ):
            db_deletepaste(getcursor(), pasteid)  # type: ignore
            return msg_paste_deleted, 200
        else:
            return msg_err_401, 401
    else:
        return "invalid http method\n"


@app.route("/<pasteid>/<token>", methods=["GET"])
def deletepaste(pasteid, token):
    result = db_getpaste(getcursor(cursor_factory=DictCursor), pasteid)  # type: ignore
    if not result:
        abort(404)
    elif result["token"] == token:  # type: ignore
        db_deletepaste(getcursor(), pasteid)  # type: ignore
        return render_template("deleted.html")
    else:
        abort(401)


@app.route("/about/api")
def aboutapi():
    return set_cache_control(
        make_response(render_template("api.html")), nonpaste_max_age
    )


@app.route("/about")
def aboutpage():
    return set_cache_control(
        make_response(render_template("about.html")), nonpaste_max_age
    )


@app.route("/stats")
def statspage():
    stats = getstats(getcursor(cursor_factory=DictCursor))  # type: ignore
    return set_cache_control(
        make_response(render_template("stats.html", stats=stats)),
        nonpaste_max_age,
    )


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500


if __name__ == '__main__':
    app.debug = False
    app.run()
