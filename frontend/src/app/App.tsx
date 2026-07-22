import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider, type RouterProviderProps } from "react-router-dom";

import { createQueryClient } from "./queryClient";
import { createAppRouter } from "./router";
import { ErrorBoundary } from "./ErrorBoundary";

interface AppProps {
  router?: RouterProviderProps["router"];
}

export function App({ router }: AppProps) {
  const [queryClient] = useState(createQueryClient);
  const [defaultRouter] = useState(createAppRouter);

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router ?? defaultRouter} />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
