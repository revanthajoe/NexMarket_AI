"use client";

import { Toaster } from "react-hot-toast";

export function ToasterProvider() {
  return (
    <Toaster
      position="bottom-right"
      toastOptions={{
        style: {
          background: "#17162a",
          color: "#e2e8f0",
          border: "1px solid #2d2b4e",
        },
      }}
    />
  );
}
