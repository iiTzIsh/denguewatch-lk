import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource/atkinson-hyperlegible-next/400.css";
import "@fontsource/atkinson-hyperlegible-next/700.css";
import "./styles.css";
import App from "./App";
import { ThemeProvider } from "./theme";

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
