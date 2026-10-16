import { Component, lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { Button } from "./components/Button";
import { Callout } from "./components/Callout";
import { Boot } from "./state/boot";
import Landing from "./pages/Landing";

const Input = lazy(() => import("./pages/Input"));
const Lists = lazy(() => import("./pages/Lists"));
const Chosen = lazy(() => import("./pages/Chosen"));

export default function App() {
  return (
    <ErrorBoundary>
      <Boot>
        <Suspense fallback={null}>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Landing />} />
              <Route path="bat-dau" element={<Input />} />
              <Route path="phuong-an" element={<Lists />} />
              <Route path="danh-sach" element={<Chosen />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </Boot>
    </ErrorBoundary>
  );
}

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page stack">
        <Callout tone="err" title="Trang gặp lỗi">Có lỗi khi hiển thị trang. Kế hoạch của em vẫn còn trong thẻ này.</Callout>
        <Button onClick={() => location.assign("/")}>Về trang đầu</Button>
      </div>
    );
  }
}
