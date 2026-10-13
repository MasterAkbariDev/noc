import { useEffect } from "react";

const APP_NAME = "NOC";

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · ${APP_NAME}`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
