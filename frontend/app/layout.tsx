import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Grounded Q&A for Internal Codebases",
  description:
    "Ask natural-language questions about a GitHub repo. Answers are grounded in retrieved code, with file + line citations.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-canvas text-ink font-body">
        {children}
      </body>
    </html>
  );
}
