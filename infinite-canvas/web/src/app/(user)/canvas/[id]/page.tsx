import { Suspense } from "react";

import CanvasClientPage from "./canvas-client-page";
import { CanvasHostSessionGuard } from "../components/canvas-host-session-guard";
import { CanvasStatusScreen } from "../components/canvas-status-screen";

export default function CanvasPage() {
    return (
        <Suspense fallback={<CanvasSessionLoading />}>
            <CanvasHostSessionGuard>
                <CanvasClientPage />
            </CanvasHostSessionGuard>
        </Suspense>
    );
}

function CanvasSessionLoading() {
    return <CanvasStatusScreen status="session" loading />;
}
