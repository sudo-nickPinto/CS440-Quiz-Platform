import { describe, expect, it } from "vitest";
import {
  ADMIN_SECTIONS,
  approvalLabel,
  approvedQuizzesPath,
  approvalButton,
  classPagePath,
  presentStatus,
  sendForApproval,
  resolveUserSection,
  myQuizzesPath,
  quizAccessLabel,
  quizStatusLabel,
  submissionPreviewPath,
  membersWithStats,
  initials,
  resolveAdminSection,
  scoreMark,
  studentRanks,
  submissionsPath,
} from "./classHelpers";

describe("myQuizzesPath", () => {
  it("asks for the caller's own and shared quizzes, recently edited first", () => {
    expect(myQuizzesPath(4)).toBe(
      "/classes/4/quizzes?mine=true&page=1&page_size=25&sort=updated_at&order=desc",
    );
  });

  it("maps sort choices and pages", () => {
    expect(myQuizzesPath(4, 3, "title")).toBe(
      "/classes/4/quizzes?mine=true&page=3&page_size=25&sort=title&order=asc",
    );
    expect(myQuizzesPath(4, 1, "newest", 100)).toContain(
      "page_size=100&sort=created_at&order=desc",
    );
  });

  it("falls back to recently edited for an unknown sort", () => {
    expect(myQuizzesPath(4, 1, "bogus")).toContain("sort=updated_at");
  });
});

describe("labels", () => {
  it("names access and status", () => {
    expect(quizAccessLabel("OWNER")).toBe("Owner");
    expect(quizAccessLabel("EDITOR")).toBe("Editor");
    expect(quizAccessLabel(null)).toBe("—");
    expect(quizStatusLabel("PUBLISHED")).toBe("Published");
    expect(quizStatusLabel("weird")).toBe("—");
  });
});

describe("approval queue helpers", () => {
  it("builds the submitted-version preview path, or null for a bad address", () => {
    expect(submissionPreviewPath(4, 9)).toBe(
      "/classes/4/dashboard/submissions/9/preview",
    );
    expect(submissionPreviewPath("4", "x")).toBeNull();
    expect(submissionPreviewPath(undefined, 9)).toBeNull();
  });

  it("builds submission paths with a sort and an optional status", () => {
    expect(submissionsPath(4, 2, "oldest", "PENDING", 10)).toBe(
      "/classes/4/dashboard/submissions?page=2&page_size=10" +
        "&sort=submitted_at&order=asc&status=PENDING",
    );
    expect(submissionsPath(4, 1, "nope", "")).toBe(
      "/classes/4/dashboard/submissions?page=1&page_size=25" +
        "&sort=submitted_at&order=desc",
    );
    expect(submissionsPath(4, 1, "title", "BOGUS")).not.toContain("status=");
  });

  it("builds approved-quiz paths", () => {
    expect(approvedQuizzesPath(9, 1, "title")).toBe(
      "/classes/9/dashboard/approved-quizzes?page=1&page_size=24" +
        "&sort=title&order=asc",
    );
  });

  it("labels every approval state", () => {
    expect(approvalLabel(null)).toBe("Not submitted");
    expect(approvalLabel("PENDING")).toBe("Waiting for approval");
    expect(approvalLabel("APPROVED")).toBe("Approved");
  });
});

describe("resolveAdminSection", () => {
  it("keeps the current tabs and defaults to Students", () => {
    for (const section of ADMIN_SECTIONS) {
      expect(resolveAdminSection(section).section).toBe(section);
    }
    expect(resolveAdminSection(null)).toEqual({
      section: "Students",
      historyView: "sessions",
    });
    expect(resolveAdminSection("Nope").section).toBe("Students");
  });

  it("maps the merged tabs onto their new homes", () => {
    expect(resolveAdminSection("Quizzes")).toMatchObject({
      section: "Presentations",
      historyView: "quizzes",
    });
    expect(resolveAdminSection("Members").section).toBe("Students");
    expect(resolveAdminSection("Settings").section).toBe("Students");
  });
});

describe("membersWithStats", () => {
  const members = [
    { account_id: 1, display_name: "Prof", email: "p@x", role: "ORGANIZER" },
    { account_id: 2, display_name: "bea", email: "b@x", role: "MEMBER" },
    { account_id: 3, display_name: "Al", email: "a@x", role: "MEMBER" },
    { account_id: 4, display_name: "", email: "cy@x", role: "MEMBER" },
  ];
  const stats = new Map([
    [2, { account_id: 2, average_score: 900 }],
    [3, { account_id: 3, average_score: 400 }],
    [4, { account_id: 4, average_score: null }],
  ]);
  const ids = (rows) => rows.map((row) => row.account_id);

  it("lists each member once with their scores; organizers have none", () => {
    const rows = membersWithStats(members, stats);
    expect(ids(rows)).toEqual([3, 2, 4, 1]);
    expect(rows.find((row) => row.account_id === 1).stats).toBeNull();
    expect(rows.find((row) => row.account_id === 2).stats.average_score).toBe(900);
  });

  it("sorts by best average with unscored members last", () => {
    expect(ids(membersWithStats(members, stats, "average"))).toEqual([2, 3, 4, 1]);
  });

  it("sorts organizers first", () => {
    expect(ids(membersWithStats(members, stats, "role"))).toEqual([1, 3, 2, 4]);
  });

  it("still lists members when scores are unavailable", () => {
    expect(ids(membersWithStats(members, null))).toEqual([3, 2, 4, 1]);
  });
});

describe("classPagePath", () => {
  it("goes to the class, or the class list when there is none", () => {
    expect(classPagePath(4)).toBe("/app/classes/4");
    expect(classPagePath("7")).toBe("/app/classes/7");
    expect(classPagePath(null)).toBe("/app/classes");
    expect(classPagePath(undefined)).toBe("/app/classes");
    expect(classPagePath("x")).toBe("/app/classes");
  });
});

describe("studentRanks", () => {
  const row = (id, average, role = "MEMBER") => ({
    account_id: id,
    role,
    stats: average === undefined ? null : { average_score: average },
  });

  it("ranks students by average, sharing ties, skipping unplayed and organizers", () => {
    const ranks = studentRanks([
      row(1, 500),
      row(2, 900),
      row(3, 500),
      row(4, null),
      row(5, undefined, "ORGANIZER"),
      row(6, 100),
    ]);
    expect(Object.fromEntries(ranks)).toEqual({ 2: 1, 1: 2, 3: 2, 6: 4 });
  });
});

describe("scoreMark", () => {
  it("marks absences, and scores against the presentation average", () => {
    expect(scoreMark(null, 500)).toBe("miss");
    expect(scoreMark(500, 500)).toBe("hi");
    expect(scoreMark(499, 500)).toBe("lo");
    expect(scoreMark(10, null)).toBe("hi");
  });
});

describe("initials", () => {
  it("takes two initials from a name or an email", () => {
    expect(initials("Ruby Castillo")).toBe("RC");
    expect(initials("ana")).toBe("AN");
    expect(initials("jo.smith@x.edu")).toBe("JS");
    expect(initials("")).toBe("?");
  });
});

describe("resolveUserSection", () => {
  it("keeps Present and Participate and sends old names to Present", () => {
    expect(resolveUserSection("Participate")).toBe("Participate");
    expect(resolveUserSection("Present")).toBe("Present");
    expect(resolveUserSection("My quizzes")).toBe("Present");
    expect(resolveUserSection(null)).toBe("Present");
  });
});

describe("presentStatus", () => {
  it("shows Approved only while the approved version is the current one", () => {
    expect(presentStatus({ status: "PUBLISHED", approval_status: "APPROVED" }).label).toBe("Approved");
    expect(presentStatus({ status: "DRAFT", approval_status: "APPROVED" }).label).toBe("Draft");
    expect(presentStatus({ status: "PUBLISHED", approval_status: "PENDING" }).label).toBe("Draft");
    expect(presentStatus({ status: "DRAFT", approval_status: null }).label).toBe("Draft");
    expect(presentStatus({ status: "ARCHIVED", approval_status: "APPROVED" }).label).toBe("Archived");
  });
});

describe("approvalButton", () => {
  const quiz = (extra) => ({
    status: "DRAFT",
    my_access: "OWNER",
    published_version_id: null,
    approval_status: null,
    approval_sent_by_me: false,
    ...extra,
  });

  it("walks send → withdraw → approved", () => {
    expect(approvalButton(quiz()).kind).toBe("send");
    expect(approvalButton(quiz()).disabled).toBe(false);
    const waiting = quiz({ status: "PUBLISHED", published_version_id: 3, approval_status: "PENDING", approval_sent_by_me: true });
    expect(approvalButton(waiting)).toMatchObject({ kind: "withdraw", disabled: false });
    const approved = quiz({ status: "PUBLISHED", published_version_id: 3, approval_status: "APPROVED" });
    expect(approvalButton(approved)).toMatchObject({ kind: "approved", disabled: true, label: "✓ Approved" });
  });

  it("lets only the sender withdraw", () => {
    const other = quiz({ status: "PUBLISHED", published_version_id: 3, approval_status: "PENDING", my_access: "EDITOR" });
    expect(approvalButton(other)).toMatchObject({ kind: "waiting", disabled: true });
  });

  it("asks again after edits or a rejection", () => {
    const edited = quiz({ published_version_id: 3, approval_status: "APPROVED" });
    expect(approvalButton(edited)).toMatchObject({ kind: "send", note: "Edited since approval" });
    const rejected = quiz({ status: "PUBLISHED", published_version_id: 3, approval_status: "REJECTED" });
    expect(approvalButton(rejected)).toMatchObject({ kind: "send", label: "Send again", note: "Rejected" });
    const withdrawn = quiz({ status: "PUBLISHED", published_version_id: 3, approval_status: "WITHDRAWN" });
    expect(approvalButton(withdrawn)).toMatchObject({ kind: "send", label: "Send for approval", note: null });
  });

  it("keeps co-editors from sending unpublished edits", () => {
    expect(approvalButton(quiz({ my_access: "EDITOR" }))).toMatchObject({ kind: "send", disabled: true });
    expect(approvalButton(quiz({ my_access: "EDITOR", status: "PUBLISHED", published_version_id: 3 })).disabled).toBe(false);
  });

  it("has nothing for archived quizzes", () => {
    expect(approvalButton(quiz({ status: "ARCHIVED" }))).toBeNull();
  });
});

describe("sendForApproval", () => {
  it("submits the published version directly", async () => {
    const calls = [];
    const api = async (url, init) => { calls.push([url, init?.body]); return {}; };
    await sendForApproval(api, 4, { quiz_id: 9, status: "PUBLISHED", published_version_id: 12 });
    expect(calls).toEqual([["/classes/4/quiz-submissions", JSON.stringify({ quiz_version_id: 12 })]]);
  });

  it("publishes a draft first, then submits the new version", async () => {
    const calls = [];
    const api = async (url, init) => {
      calls.push(url);
      if (url === "/quizzes/9") return { revision: 5 };
      if (url.endsWith("/publish")) {
        expect(init.body).toBe(JSON.stringify({ expected_revision: 5 }));
        return { version: { quiz_version_id: 13 } };
      }
      expect(init.body).toBe(JSON.stringify({ quiz_version_id: 13 }));
      return {};
    };
    await sendForApproval(api, 4, { quiz_id: 9, status: "DRAFT", published_version_id: 12 });
    expect(calls).toEqual(["/quizzes/9", "/classes/4/quizzes/9/publish", "/classes/4/quiz-submissions"]);
  });
});
