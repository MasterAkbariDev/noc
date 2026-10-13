import { Component, type ReactNode } from "react";
import { ErrorState } from "../ui/ErrorState";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  failed: boolean;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  render(): ReactNode {
    if (this.state.failed) {
      return (
        <ErrorState
          title="Something went wrong"
          message="This page could not be shown. Reload the page to try again."
          onRetry={() => window.location.reload()}
        />
      );
    }
    return this.props.children;
  }
}
