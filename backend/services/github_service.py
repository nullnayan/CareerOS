"""
GitHub Service — handles all GitHub API interactions.

Responsibilities:
1. Exchange OAuth code for access token.
2. Fetch authenticated user profile.
3. Create repositories (public or private).
4. Push files to a repository (create blobs, trees, commits, update refs).

Uses raw httpx calls instead of PyGithub to keep dependencies minimal
and give you full visibility into what's happening at the API level —
important for interview explanations.
"""

import logging
from typing import List, Optional
import base64

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def exchange_code_for_token(
    code: str, client_id: str, client_secret: str
) -> dict:
    """
    Exchange the OAuth authorization code for an access token.
    Returns the full response dict from GitHub (includes access_token, scope, token_type).
    """
    response = httpx.post(
        "https://github.com/login/oauth/access_token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(
            f"GitHub OAuth error: {data.get('error_description', data['error'])}"
        )

    return data


def get_user_profile(access_token: str) -> dict:
    """Fetch the authenticated user's GitHub profile."""
    response = httpx.get(
        f"{GITHUB_API}/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()


def create_repository(
    access_token: str,
    repo_name: str,
    description: str = "",
    private: bool = False,
) -> dict:
    """
    Create a new repository on the authenticated user's account.
    Returns the full repo object from GitHub.
    """
    response = httpx.post(
        f"{GITHUB_API}/user/repos",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": True,  # Creates an initial commit with README
        },
        timeout=30.0,
    )

    if response.status_code == 422:
        # Usually means repo already exists
        error_data = response.json()
        errors = error_data.get("errors", [])
        if any(e.get("message", "").startswith("name already exists") for e in errors):
            raise ValueError(
                f"Repository '{repo_name}' already exists on your GitHub account. "
                f"Choose a different name."
            )
        raise RuntimeError(f"GitHub API error: {error_data}")

    response.raise_for_status()
    return response.json()


def push_files_to_repo(
    access_token: str,
    owner: str,
    repo_name: str,
    files: List[dict],
    commit_message: str = "Add files via CareerOS",
) -> dict:
    """
    Push multiple files to a repository in a single commit.

    files: list of {"path": "relative/path.py", "content": "file content string"}

    How this works (Git Data API):
    1. Get the latest commit SHA on the default branch.
    2. Get the tree SHA from that commit.
    3. Create blobs for each file.
    4. Create a new tree with those blobs.
    5. Create a new commit pointing to the new tree.
    6. Update the branch ref to point to the new commit.

    This is the same process `git add . && git commit && git push` does,
    just via the API instead of the CLI.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }

    # 1. Get default branch and latest commit
    repo_resp = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo_name}",
        headers=headers,
        timeout=15.0,
    )
    repo_resp.raise_for_status()
    default_branch = repo_resp.json().get("default_branch", "main")

    ref_resp = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo_name}/git/ref/heads/{default_branch}",
        headers=headers,
        timeout=15.0,
    )
    ref_resp.raise_for_status()
    latest_commit_sha = ref_resp.json()["object"]["sha"]

    # 2. Get the tree SHA from the latest commit
    commit_resp = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo_name}/git/commits/{latest_commit_sha}",
        headers=headers,
        timeout=15.0,
    )
    commit_resp.raise_for_status()
    base_tree_sha = commit_resp.json()["tree"]["sha"]

    # 3. Create blobs for each file
    tree_items = []
    for file_info in files:
        blob_resp = httpx.post(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/git/blobs",
            headers=headers,
            json={
                "content": base64.b64encode(file_info["content"].encode()).decode(),
                "encoding": "base64",
            },
            timeout=30.0,
        )
        blob_resp.raise_for_status()
        blob_sha = blob_resp.json()["sha"]

        tree_items.append({
            "path": file_info["path"],
            "mode": "100644",  # Regular file
            "type": "blob",
            "sha": blob_sha,
        })

    # 4. Create a new tree
    tree_resp = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo_name}/git/trees",
        headers=headers,
        json={
            "base_tree": base_tree_sha,
            "tree": tree_items,
        },
        timeout=30.0,
    )
    tree_resp.raise_for_status()
    new_tree_sha = tree_resp.json()["sha"]

    # 5. Create a new commit
    new_commit_resp = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo_name}/git/commits",
        headers=headers,
        json={
            "message": commit_message,
            "tree": new_tree_sha,
            "parents": [latest_commit_sha],
        },
        timeout=30.0,
    )
    new_commit_resp.raise_for_status()
    new_commit_sha = new_commit_resp.json()["sha"]

    # 6. Update the branch reference
    update_ref_resp = httpx.patch(
        f"{GITHUB_API}/repos/{owner}/{repo_name}/git/refs/heads/{default_branch}",
        headers=headers,
        json={"sha": new_commit_sha},
        timeout=15.0,
    )
    update_ref_resp.raise_for_status()

    logger.info(
        f"Pushed {len(files)} file(s) to {owner}/{repo_name} "
        f"(commit {new_commit_sha[:8]})"
    )

    return {
        "commit_sha": new_commit_sha,
        "repo_url": f"https://github.com/{owner}/{repo_name}",
        "files_pushed": len(files),
    }
