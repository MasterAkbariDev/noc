import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { errorMessage } from "../../lib/format";
import { ErrorState, Skeleton } from "../../ui";

type QueryBodyProps<Data> = {
  query: UseQueryResult<Data, Error>;
  failure: string;
  children: (data: Data) => ReactNode;
};

export function QueryBody<Data>({ query, failure, children }: QueryBodyProps<Data>) {
  if (query.isSuccess) {
    return <>{children(query.data)}</>;
  }
  if (query.isError) {
    return <ErrorState title={failure} message={errorMessage(query.error)} onRetry={() => void query.refetch()} />;
  }
  return <Skeleton lines={4} />;
}
