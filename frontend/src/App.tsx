import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/shared/Layout";
import { Dashboard } from "./pages/Dashboard";
import { JobRoles } from "./pages/JobRoles";
import { RankingDetail } from "./pages/RankingDetail";
import { UploadPage } from "./pages/UploadPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="jobs" element={<JobRoles />} />
          <Route path="jobs/:id/rank" element={<RankingDetail />} />
          <Route path="jobs/:id/upload" element={<UploadPage />} />
          <Route path="jobs/:id" element={<RankingDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
