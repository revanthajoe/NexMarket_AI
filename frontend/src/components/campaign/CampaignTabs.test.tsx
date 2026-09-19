import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PostingTab, AdCopyTab } from "./CampaignTabs";
import type { SocialPost, AdCopy } from "@/lib/api";

// AdCopyTab's mount effect calls api.brandKit.get(campaignId), which goes
// through the real fetch-based api client. Reject it so the effect's own
// .catch() swallows it silently, exactly like a campaign with no brand kit yet.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no backend in tests")));
});

function makePost(overrides: Partial<SocialPost> = {}): SocialPost {
  return {
    id: "post-1",
    campaign_id: "c1",
    platform: "instagram",
    status: "posted",
    retry_count: 0,
    is_mock: false,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function makeAdCopy(overrides: Partial<AdCopy> = {}): AdCopy {
  return {
    id: "copy-1",
    campaign_id: "c1",
    platform: "instagram",
    body: "Great product, get yours today!",
    cta_variants: [],
    hashtags: [],
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("PostingTab", () => {
  it("renders a checkbox for every supported platform, instagram checked by default", () => {
    render(
      <PostingTab posts={[]} campaignId="c1" copies={[]} posters={[]} onPost={vi.fn()} loading={false} />
    );
    for (const label of ["Instagram", "Facebook", "Telegram", "Whatsapp"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes.filter(c => c.checked)).toHaveLength(1);
    expect(screen.getByText("Instagram").closest("label")?.querySelector("input")).toHaveProperty("checked", true);
  });

  it("calls onPost with every selected platform when Post Now is clicked", () => {
    const onPost = vi.fn();
    render(
      <PostingTab posts={[]} campaignId="c1" copies={[]} posters={[]} onPost={onPost} loading={false} />
    );
    fireEvent.click(screen.getByText("Telegram"));
    fireEvent.click(screen.getByText(/Post Now/));
    expect(onPost).toHaveBeenCalledTimes(1);
    const [platforms] = onPost.mock.calls[0];
    expect(platforms).toEqual(expect.arrayContaining(["instagram", "telegram"]));
    expect(platforms).toHaveLength(2);
  });

  it("disables Post Now once every platform is deselected", () => {
    render(
      <PostingTab posts={[]} campaignId="c1" copies={[]} posters={[]} onPost={vi.fn()} loading={false} />
    );
    fireEvent.click(screen.getByText("Instagram")); // deselect the only checked platform
    expect(screen.getByText(/Post Now/).closest("button")).toBeDisabled();
  });

  it("renders each post's status independently — one platform's failure doesn't hide another's success", () => {
    const posts = [
      makePost({ id: "p1", platform: "instagram", status: "posted" }),
      makePost({ id: "p2", platform: "telegram", status: "failed" }),
    ];
    render(
      <PostingTab posts={posts} campaignId="c1" copies={[]} posters={[]} onPost={vi.fn()} loading={false} />
    );
    expect(screen.getByText("instagram")).toBeInTheDocument();
    expect(screen.getByText("telegram")).toBeInTheDocument();
    expect(screen.getByText("posted")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows a mock badge for posts made in mock mode", () => {
    const posts = [makePost({ is_mock: true })];
    render(
      <PostingTab posts={posts} campaignId="c1" copies={[]} posters={[]} onPost={vi.fn()} loading={false} />
    );
    expect(screen.getByText("mock")).toBeInTheDocument();
  });
});

describe("AdCopyTab", () => {
  it("shows the fallback badge when the selected copy failed generation", () => {
    const copies = [makeAdCopy({ fallback: true })];
    render(<AdCopyTab copies={copies} campaignId="c1" onGenerate={vi.fn()} loading={false} />);
    expect(screen.getByText("fallback")).toBeInTheDocument();
  });

  it("does not show the fallback badge for a real generation result", () => {
    const copies = [makeAdCopy({ fallback: false })];
    render(<AdCopyTab copies={copies} campaignId="c1" onGenerate={vi.fn()} loading={false} />);
    expect(screen.queryByText("fallback")).not.toBeInTheDocument();
  });
});
