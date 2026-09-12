import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ProvenanceProvider } from "./components/ProvenancePanel";
import "./styles/tokens.css";
import "./styles/console.css";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 60_000 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ProvenanceProvider>
          <App />
        </ProvenanceProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
