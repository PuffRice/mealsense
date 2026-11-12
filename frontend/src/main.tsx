import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./design/tokens.css";
import "./design/styles.css";
import App from "./App";
import { DoctorPortal } from "./features/doctor/DoctorPortal";

// The public doctor access page lives outside the patient app shell.
const path = window.location.pathname.replace(/\/+$/, "");
const root = createRoot(document.getElementById("root")!);

if (path === "/doctor") {
  root.render(
    <StrictMode>
      <DoctorPortal />
    </StrictMode>,
  );
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
