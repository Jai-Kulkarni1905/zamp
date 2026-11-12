import { createBrowserRouter, Link, Navigate, Outlet, RouterProvider } from "react-router";
import { TopBar } from "./components/TopBar";
import { RunPage } from "./pages/RunPage";
import { DashboardPage } from "./pages/DashboardPage";

function Layout() {
  return (
    <div className="min-h-screen">
      <TopBar />
      <main>
        <Outlet />
      </main>
    </div>
  );
}

function NotFound() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <p className="text-base font-semibold">Page not found</p>
      <Link to="/" className="mt-2 inline-block text-sm text-accent-700 hover:underline">
        Back to dashboard
      </Link>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/upload", element: <Navigate to="/" replace /> },
      { path: "/run/:id", element: <RunPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
