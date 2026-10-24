// These hooks intentionally make no requests until the class API
// contracts are implemented and verified.
//
// "Unavailable" is different from a successful response containing
// an empty list. Do not substitute [] or invented records here.

const UNAVAILABLE = Object.freeze({
  status: "unavailable",
  data: null,
  error: null,
  reload: null,
});

const INVALID_CLASS = Object.freeze({
  status: "error",
  data: null,
  error: new Error("This class address is invalid."),
  reload: null,
});

export function useClassesResource() {
  return UNAVAILABLE;
}

export function useClassResource(classId) {
  if (!/^[1-9]\d*$/.test(String(classId ?? ""))) {
    return INVALID_CLASS;
  }

  return UNAVAILABLE;
}
