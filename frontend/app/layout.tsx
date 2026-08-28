import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider, themeInitScript } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Grounded Q&A for Internal Codebases",
  description:
    "Ask natural-language questions about a GitHub repo. Answers are grounded in retrieved code, with file + line citations.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <head>
        {/* Runs before hydration so the correct theme applies on first paint
            — without this, the page would flash light mode before React
            mounts and ThemeProvider syncs to the stored/system preference.
            suppressHydrationWarning above is required because of this: the
            script mutates <html>'s class on the real DOM before React
            hydrates, so the server-rendered className (which never included
            "dark") legitimately won't match what's actually in the DOM by
            the time hydration runs. That's expected for this pattern, not a
            bug — suppressHydrationWarning tells React to trust the DOM over
            its own server-rendered snapshot for just this one attribute. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-full flex flex-col bg-canvas text-ink font-body">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
