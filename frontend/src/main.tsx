import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { installPreloadErrorRecovery } from "./app/chunkRecovery";
import "./styles/tokens.css";
import "./styles/global.css";

installPreloadErrorRecovery();

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Application root element was not found.");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
