import { Navigate, Route, Routes } from 'react-router-dom'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<div>Login</div>} />
      <Route path="/register" element={<div>Register</div>} />
      <Route path="/workspace" element={<div>Workspace</div>} />
      <Route path="*" element={<Navigate to="/workspace" replace />} />
    </Routes>
  )
}
