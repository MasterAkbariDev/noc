import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { SessionProvider } from "./auth/session";
import { Toaster, TooltipProvider } from "./ui";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
});

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("missing #root element");
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster>
          <BrowserRouter>
            <SessionProvider>
              <App />
            </SessionProvider>
          </BrowserRouter>
        </Toaster>
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
);
