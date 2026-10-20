import React, { useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import LocationSelectionPage from './LocationSelectionPage.jsx';

function RedirectToDashboard({ path }) {
  useEffect(() => {
    window.location.href = `http://127.0.0.1:8000${path}`;
  }, [path]);
  return null;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<LocationSelectionPage />} />
      <Route path="/welcome" element={<LocationSelectionPage />} />
      <Route path="/location" element={<LocationSelectionPage />} />
      <Route path="/dashboard" element={<RedirectToDashboard path="/dashboard" />} />
      <Route path="/analysis" element={<RedirectToDashboard path="/analysis" />} />
      <Route path="*" element={<LocationSelectionPage />} />
    </Routes>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
