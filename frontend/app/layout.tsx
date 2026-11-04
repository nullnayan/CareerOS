import "./globals.css";
import { WorkspaceProvider } from "./context/WorkspaceContext";
import LayoutClient from "./components/LayoutClient";

export const metadata = {
  title: "CareerOS",
  description:
    "Upload resumes, analyse ATS compatibility, track skills, and tailor applications to a job.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <WorkspaceProvider>
          <LayoutClient>{children}</LayoutClient>
        </WorkspaceProvider>
      </body>
    </html>
  );
}
