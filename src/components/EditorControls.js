import { useState, useEffect, useCallback } from "react";
import styled from "styled-components";
import { gzip } from "pako";
import history from "history/browser";
import copy from "copy-to-clipboard";

import { languages } from "../utils/langs";
import themes from "../style/theme";
import { postUrl } from "../utils/constants";

export default function EditorControls({
    actualContent,
    setForcedContent,
    language,
    setLanguage,
    readOnly,
    setReadOnly,
    theme,
    setTheme,
    zoom,
}) {
    const [saving, setSaving] = useState(false);
    const [recentlySaved, setRecentlySaved] = useState(false);

    useEffect(() => {
        setRecentlySaved(false);
    }, [actualContent, language]);

    const save = useCallback(() => {
        if (!actualContent || recentlySaved) {
            return;
        }
        setSaving(true);
        saveToBytebin(actualContent, language).then(pasteId => {
            setSaving(false);
            setRecentlySaved(true);
            if (pasteId) {
                history.replace({
                    pathname: pasteId,
                });
                copy(window.location.href);
                document.title = "Melon Paste | " + pasteId;
            }
        });
    }, [actualContent, language, recentlySaved]);

    useEffect(() => {
        const listener = e => {
            if (e.ctrlKey || e.metaKey) {
                if (e.key === "s" || e.key === "s") {
                    e.preventDefault();
                    save();
                }

                if (e.key === "=" || e.key === "-") {
                    e.preventDefault();
                    zoom(e.key === "=" ? 1 : -1);
                }
            }
        };

        window.addEventListener("keydown", listener);
        return () => window.removeEventListener("keydown", listener);
    }, [save, zoom]);

    function reset() {
        setForcedContent("");
        setLanguage("plain");
        history.replace({
            pathname: "/",
            hash: "",
        });
        document.title = "paste";
    }

    function unsetReadOnly() {
        setReadOnly(false);
    }

    return (
        <Header>
            <Section>
                <Button onClick={reset}>[new]</Button>
                <Button onClick={save}>
                    {recentlySaved ? "[link copied!]" : saving ? "[saving...]" : "[save]"}
                </Button>
                <MenuButton
                    label="language"
                    value={language}
                    setValue={setLanguage}
                    ids={languages}
                />
                {readOnly && <Button onClick={unsetReadOnly}>[edit]</Button>}
            </Section>
            <Section>
                <Button onClick={() => zoom(1)}>[+ </Button>
                <Button onClick={() => zoom(-1)}> -]</Button>
                <MenuButton
                    label="theme"
                    value={theme}
                    setValue={setTheme}
                    ids={Object.keys(themes)}
                />
                <Button
                    className="optional"
                    as="a"
                    href="https://github.com/Melon-Development-ZUI/pastebin#readme"
                    target="_blank"
                    rel="noreferrer"
                >
                    [about]
                </Button>
            </Section>
        </Header>
    );
}

const Header = styled.header`
    position: fixed;
    top: 0;
    z-index: 2;
    width: 100%
    height: 2em;
    color: ${props => props.theme.primary};
    background: ${props => props.theme.secondary};
    display: flex;
    justify-content: space-between;
    user-select: none;
`;

const Section = styled.div`
    display: flex;
    align-items: center;

    @media (max-width: 470px) {
        .optional {
            display: none;
        }
    }
`;

function languageToContentType(language) {
    if (language === "json") {
        return "application/json";
    } else {
        return "text/" + language;
    }
}

async function saveToBytebin(code, language) {
    try {
        const compressed = gzip(code);
        const contentType = languageToContentType(language);

        const resp = await fetch(postUrl, {
            method: "POST",
            headers: {
                "Content-Type": contentType,
                "Content-Encoding": "gzip",
                "Accept": "applicationjson",
            },
            body: compressed,
        });

        if (resp.ok) {
            const json = await resp.json();
            return json.key;
        }
    } catch (e) {
        console.log(e);
    }
    return null;
}
