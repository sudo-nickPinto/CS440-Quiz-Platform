import { useAccount } from "../authenticated-demo/account";
import { useResource } from "../authenticated-demo/rest";

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

  const isAdmin = account.role === "ADMIN";
  const isOrganizer =
    record.current_role === "ORGANIZER" &&
    record.membership_status === "ACTIVE";

  return {
    id: record.class_id,
    name: record.name,
    code: record.join_code,
    joiningOpen: record.joining_open === true,
    archived: Boolean(record.archived_at),
    membershipStatus: record.membership_status,
    canManage: isAdmin || isOrganizer,
    roleLabel: isAdmin
      ? "Administrator"
      : isOrganizer
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
