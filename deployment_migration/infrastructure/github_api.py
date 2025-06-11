import subprocess
from typing import Self

from deployment_migration.application import GithubApi


class GithubApiImplementation(GithubApi):
    def _run_cmd(self, cmd):
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def ensure_authenticated(self: Self) -> None:
        code, _, _ = self._run_cmd("gh auth status")
        if code != 0:
            print("Not authenticated. Running 'gh auth login' (follow prompts in browser)...")
            self._run_cmd("gh auth login --web")
        else:
            print("Already authenticated.")

    def environment_exists(self, repo, environment):
        code, _, _ = self._run_cmd(f'gh api "repos/{repo}/environments/{environment}"')
        return code == 0

    def create_environment(self: Self, repo: str, environment: str) -> None:
        if self.environment_exists(repo, environment):
            print(f"Environment '{environment}' already exists, skipping.")
        else:
            print(f"Creating environment: {environment} in repository: {repo}")
            code, _, err = self._run_cmd(f'gh api -X PUT "repos/{repo}/environments/{environment}"')
            if code != 0:
                if "409" in err:
                    # No need to print anything, environment already exists
                    return
                print(f"Could not create environment '{environment}': {err}")

    def add_variable_to_environment(self: Self, repo: str, environment: str, name: str, value: str) -> None:
        print(f"Adding variable '{name}' with value='{value}' to environment '{environment}' "
              f"(will overwrite if exists)...\n")
        code, _, err = self._run_cmd(
            f'gh api -X POST repos/{repo}/environments/{environment}/variables -f "name={name}" -f "value={value}"')
        if code != 0:
            if "409" in err:
                # No need to print anything, environment already exists
                return
            print(f"Could not add variable '{name}' to environment '{environment}': {err}")
