"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "@/lib/api";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Retrying a 4xx (bad auth, not found, bad request) can never
            // succeed — only retry on network/5xx failures, and cap it low.
            retry: (failureCount, error) => {
              if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
                return false;
              }
              return failureCount < 2;
            },
            // Default `networkMode: "online"` pauses retries indefinitely
            // whenever the browser's online-detection is unreliable (true
            // in some embedded/sandboxed webviews) instead of surfacing an
            // error. We always have a real connection to the API here.
            networkMode: "always",
          },
        },
      })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
