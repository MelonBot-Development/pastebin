import { useState, useEffect } from "react";
import { ThemeProvider, createGlobalStyle } from "styled-components";
import { isMobile } from "react-device-detect";
import ls from "local-storage";

import EditorControls from "./EditorControls";
import EditorTextArea from "./EditorTextArea";
import themes from "../style/theme";