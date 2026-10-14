export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

const USERNAME_PATTERN = /^[a-z0-9][a-z0-9._-]{2,31}$/;

export function passwordProblem(password: string): string | null {
  const length = Array.from(password).length;
  return length >= PASSWORD_MIN_LENGTH && length <= PASSWORD_MAX_LENGTH
    ? null
    : `Use ${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters.`;
}

export function confirmationProblem(password: string, confirmation: string): string | null {
  return password === confirmation ? null : "The two passwords do not match.";
}

export function normalizeUsername(name: string): string {
  return name.trim().toLowerCase();
}

export function usernameProblem(name: string): string | null {
  return USERNAME_PATTERN.test(normalizeUsername(name))
    ? null
    : "Use 3 to 32 letters, digits, dots, dashes or underscores. Start with a letter or a digit.";
}
