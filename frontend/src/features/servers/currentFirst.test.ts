import { describe, expect, it } from "vitest";
import { currentFirst } from "./ServersList";
import { summaryFixture } from "./fixtures";

describe("currentFirst", () => {
  it("puts the server this panel runs on first and keeps the rest in order", () => {
    const servers = [
      summaryFixture({ name: "demo-1", tag: null }),
      summaryFixture({ name: "prod-46", tag: "current" }),
      summaryFixture({ name: "db-2", tag: null }),
    ];

    expect(currentFirst(servers).map((server) => server.name)).toEqual(["prod-46", "demo-1", "db-2"]);
  });
});
