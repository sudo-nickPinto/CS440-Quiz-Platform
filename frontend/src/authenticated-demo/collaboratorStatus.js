// Whether a collaborator search result is an editor of the quiz right now.
//
// `changes` holds what this pop-up just did, by account_id: true after
// adding them, false after removing them. It wins over the result's own
// `is_collaborator`, which may be from before the change until the search
// is asked again.
export function isEditorNow(person, changes) {
  const changed = changes?.[person.account_id];
  return typeof changed === "boolean" ? changed : Boolean(person.is_collaborator);
}

// `changes` after adding (true) or removing (false) one account.
export function withEditorChange(changes, accountId, isEditor) {
  return { ...changes, [accountId]: isEditor };
}
