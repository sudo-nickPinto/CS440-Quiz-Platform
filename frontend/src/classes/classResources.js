import { useAccount } from "../authenticated-demo/account";
import { useEffect, useState } from "react";
import { useApi, useResource } from "../authenticated-demo/rest";
import {
  approvedQuizzesPath,
  myQuizzesPath,
  submissionsPath,
} from "./classHelpers";

function normalizeClass(record, account) {
  if (
    !record ||
    !Number.isSafeInteger(record.class_id) ||
    record.class_id < 1 ||
    typeof record.name !== "string" ||
    !record.name.trim()
  ) {
    throw new Error("The server returned invalid class information.");
  }

  const isFaculty = account.is_active === true && account.role === "ADMIN";

  const isOrganizer =
    isFaculty &&
    record.current_role === "ORGANIZER" &&
    record.membership_status === "ACTIVE";
  return {
    id: record.class_id,
    name: record.name,
    code: record.join_code,
    joiningOpen: record.joining_open === true,
    archived: Boolean(record.archived_at),
    membershipStatus: record.membership_status,
    canManage: isOrganizer,
    roleLabel: isOrganizer
      ? "Organizer"
      : record.membership_status === "INVITED"
        ? "Invited"
        : "Member",
  };
}

function resourceState(result, transform) {
  const base = {
    data: null,
    error: result.error,
    reload: result.reload,
  };

  if (result.loading) {
    return { ...base, status: "loading" };
  }

  if (result.error) {
    const status =
      result.error.status === 403
        ? "forbidden"
        : result.error.status === 404
          ? "not-found"
          : "error";

    return { ...base, status };
  }

  try {
    return {
      ...base,
      status: "ready",
      data: transform(result.data),
    };
  } catch (error) {
    return {
      ...base,
      status: "error",
      error,
    };
  }
}

export function useClassesResource() {
  const account = useAccount();
  const result = useResource("/classes");

  return resourceState(result, (data) => {
    if (!Array.isArray(data)) {
      throw new Error("The class list could not be read.");
    }

    return data.map((record) => normalizeClass(record, account));
  });
}

export function useClassResource(classId) {
  const account = useAccount();

  const valid =
    /^[1-9]\d*$/.test(String(classId ?? "")) &&
    Number.isSafeInteger(Number(classId));

  // Always call the hook, but do not request an invalid class address.
  const result = useResource(valid ? `/classes/${classId}` : null);

  if (!valid) {
    return {
      status: "error",
      data: null,
      error: new Error("This class address is invalid."),
      reload: null,
    };
  }

  return resourceState(result, (data) => normalizeClass(data, account));
}

export const REPORT_PAGE_SIZE = 25;

function useClassReport(classId, path, pollMs = 0) {
  const result = useResource(`/classes/${classId}/${path}`, pollMs);

  return resourceState(result, (data) => {
    if (!data || typeof data !== "object") {
      throw new Error("The class report could not be read.");
    }

    return data;
  });
}

// Polled so counts such as the pending-approval badge pick up changes
// other people make (a student sending a quiz for approval).
export const DASHBOARD_POLL_MS = 30000;

export function useClassDashboard(classId) {
  return useClassReport(classId, "dashboard", DASHBOARD_POLL_MS);
}

export function useClassSessions(classId, page = 1) {
  return useClassReport(
    classId,
    `sessions?page=${page}&page_size=${REPORT_PAGE_SIZE}`,
  );
}

// Every student's scores, keyed by account id, for the Students tab. The
// students report is paged (at most 100 a page), so read every page.
export function useClassStudentStats(classId) {
  const api = useApi();
  const [revision, setRevision] = useState(0);
  const key = `${classId}:${revision}`;
  const [result, setResult] = useState({ key: null, data: null, error: null });

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const byId = new Map();
        let page = 1;
        let totalPages = 1;
        do {
          const data = await api(
            `/classes/${classId}/students?page=${page}&page_size=100&sort=name&order=asc`,
            { signal: controller.signal },
          );
          if (!data || !Array.isArray(data.items)) {
            throw new Error("The student scores could not be read.");
          }
          for (const student of data.items) {
            byId.set(Number(student.account_id), student);
          }
          totalPages = data.pagination?.total_pages ?? 1;
          page += 1;
        } while (page <= totalPages);

        if (!controller.signal.aborted) {
          setResult({ key, data: byId, error: null });
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setResult({ key, data: null, error });
        }
      }
    }

    void load();
    return () => controller.abort();
  }, [api, classId, key]);

  const current = result.key === key;
  return {
    data: current ? result.data : null,
    error: current ? result.error : null,
    loading: !current,
    reload: () => setRevision((value) => value + 1),
  };
}

export function useClassQuizzes(classId, page = 1) {
  return useClassReport(
    classId,
    `presented-quizzes?page=${page}&page_size=${REPORT_PAGE_SIZE}&sort=presented_at&order=desc`,
  );
}

// Quizzes in this class the caller owns or collaborates on.
export function useMyClassQuizzes(classId, page = 1, sortKey = "recent") {
  const result = useResource(myQuizzesPath(classId, page, sortKey, REPORT_PAGE_SIZE));

  return resourceState(result, (data) => {
    if (!data || !Array.isArray(data.items)) {
      throw new Error("Your quizzes could not be read.");
    }

    return data;
  });
}

function usePagedReport(path, what) {
  const result = useResource(path);

  return resourceState(result, (data) => {
    if (!data || !Array.isArray(data.items)) {
      throw new Error(`${what} could not be read.`);
    }

    return data;
  });
}

// Organizers get every submission in the class; members only their own.
export function useClassSubmissions(classId, page = 1, sortKey = "newest", status = "") {
  return usePagedReport(
    submissionsPath(classId, page, sortKey, status, REPORT_PAGE_SIZE),
    "Quiz submissions",
  );
}

// Approved quizzes any active member can see; can_host marks the ones the
// caller may start.
export function useApprovedQuizzes(classId, page = 1, sortKey = "recent") {
  return usePagedReport(
    approvedQuizzesPath(classId, page, sortKey),
    "Approved quizzes",
  );
}
