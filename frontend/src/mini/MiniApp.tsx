import { Outlet } from "react-router-dom";
import { MiniAuthProvider } from "./auth";
import { MiniLayout } from "./components/MiniLayout";
import { MiniAuthGate } from "./components/MiniAuthGate";
export { MiniHomePage } from "./pages/HomePage";
export { MiniFilesPage } from "./pages/FilesPage";
export { MiniGrantsPage } from "./pages/GrantsPage";
export { MiniVerifyPage } from "./pages/VerifyPage";
export { MiniPublicLinkPage } from "./pages/PublicLinkPage";

export function MiniApp() {
  return (
    <MiniAuthProvider>
      <MiniLayout>
        <MiniAuthGate>
          <Outlet />
        </MiniAuthGate>
      </MiniLayout>
    </MiniAuthProvider>
  );
}
