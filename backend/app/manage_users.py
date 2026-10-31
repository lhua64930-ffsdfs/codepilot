"""Provision/revoke personal access tokens without a public registration endpoint."""
import argparse
import secrets
from uuid import UUID

from app.db.models import Repository, RepositoryMember, User
from app.db.session import SessionLocal, engine
from app.db.schema import verify_schema
from app.services.authentication import token_hash
from app.services.permissions import ROLE_PERMISSIONS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--role", choices=list(ROLE_PERMISSIONS), default="viewer")
    parser.add_argument("--repo", action="append", default=[], help="Repository UUID; repeat to grant multiple repositories")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    verify_schema(engine)
    with SessionLocal() as db:
        users = db.query(User).filter_by(name=args.name).all()
        if len(users) > 1:
            parser.error("用户名称不唯一，请先修复重复记录")
        user = users[0] if users else User(name=args.name)
        repo_ids = [UUID(value) for value in args.repo]
        for repo_id in repo_ids:
            if db.get(Repository, repo_id) is None:
                parser.error(f"仓库不存在：{repo_id}")
        user.role = args.role
        token = secrets.token_urlsafe(32)
        user.api_token_hash = None if args.revoke else token_hash(token)
        db.add(user)
        db.flush()
        db.query(RepositoryMember).filter_by(user_id=user.id).delete()
        db.add_all(RepositoryMember(user_id=user.id, repo_id=repo_id) for repo_id in set(repo_ids))
        db.commit()
        print("访问令牌已撤销" if args.revoke else f"访问令牌（仅显示一次）：{token}")


if __name__ == "__main__":
    main()
