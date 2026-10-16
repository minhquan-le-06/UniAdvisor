import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import App from "./App";
import { ToastProvider } from "./components/Toast";
import "./styles/base.css";

// The style page exists only in development builds.
const StyleGuide = import.meta.env.DEV ? lazy(() => import("./pages/StyleGuide")) : null;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <BrowserRouter>
        <Suspense fallback={null}>
          <Routes>
            {StyleGuide && <Route path="/_mau" element={<StyleGuide />} />}
            <Route path="*" element={<App />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ToastProvider>
  </StrictMode>,
);
