import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { CampaignPipelineStatus } from "@/components/campaign/CampaignPipelineStatus";

describe("Phase 12 truthfulness primitives", () => {
  it("renders the requested provenance label", () => {
    render(<ProvenanceBadge value="FORECAST" />);
    expect(screen.getByText("FORECAST")).toBeInTheDocument();
  });

  it("shows pending pipeline state without claiming completion", () => {
    render(
      <CampaignPipelineStatus
        stages={[
          { label: "Publish", state: "complete" },
          { label: "Analytics", state: "pending", note: "ACTUAL data only" },
        ]}
      />,
    );
    expect(screen.getByText("Analytics")).toBeInTheDocument();
    expect(screen.getByText("ACTUAL data only")).toBeInTheDocument();
    expect(screen.queryByText("completed")).not.toBeInTheDocument();
  });

  it("supports explicit waiting and unavailable states", () => {
    const { rerender } = render(<ProvenanceBadge value="WAITING" />);
    expect(screen.getByText("WAITING")).toBeInTheDocument();
    rerender(<ProvenanceBadge value="UNAVAILABLE" />);
    expect(screen.getByText("UNAVAILABLE")).toBeInTheDocument();
  });
});
