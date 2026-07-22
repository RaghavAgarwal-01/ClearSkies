import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './hooks/useTheme';
import './premium-additions.css';
import Layout from './components/layout/Layout';
import DashboardPage from './pages/DashboardPage';
import ForecastPage from './pages/ForecastPage';
import HotspotsPage from './pages/HotspotsPage';
import AdminPage from './pages/AdminPage';
import CitizenPage from './pages/CitizenPage';
import AnalyticsPage from './pages/AnalyticsPage';

export default function App() {
  return (
    <ThemeProvider>          {/* ← add */}
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/forecast" element={<ForecastPage />} />
            <Route path="/hotspots" element={<HotspotsPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/citizen" element={<CitizenPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
