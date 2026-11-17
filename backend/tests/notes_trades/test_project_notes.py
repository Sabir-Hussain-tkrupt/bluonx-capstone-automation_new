"""Project notes API."""

from __future__ import annotations

from uuid import uuid4

from tests.financial._memdb import MemDB
from tests.notes_trades.conftest import ADMIN, PM, identity

NOW = "2026-11-17T00:00:00+00:00"
PROJECT = {"id": str(uuid4()), "archived_at": None, "deleted_at": None}


class _NotesDB(MemDB):
    """MemDB that fills the column defaults the database would."""

    def table(self, name):
        q = super().table(name)
        run = q.execute

        def execute():
            r = run()
            if name == "project_notes":
                for row in self.tables.get(name, []):
                    for k, v in (("created_at", NOW), ("updated_at", NOW), ("updated_by", None), ("deleted_at", None)):
                        row.setdefault(k, v)
                if r is not None and isinstance(r.data, list):
                    for row in r.data:
                        for k, v in (("created_at", NOW), ("updated_at", NOW), ("updated_by", None)):
                            row.setdefault(k, v)
            return r

        q.execute = execute
        return q


def _db(notes=None, project=None):
    return _NotesDB({
        "projects": [project or PROJECT],
        "project_notes": notes or [],
        "users": [{"id": PM["user_id"], "full_name": "Pat PM"},
                  {"id": ADMIN["user_id"], "full_name": "Ada Admin"}],
    })


def _note(author=PM["user_id"], **kw):
    base = {"id": str(uuid4()), "project_id": PROJECT["id"], "title": "Kick-off",
            "content_html": "<p>Hi</p>", "content_text": "Hi", "created_by": author,
            "updated_by": None, "created_at": NOW, "updated_at": NOW, "deleted_at": None}
    base.update(kw)
    return base


def test_any_user_can_add_a_document_sized_rich_note(fin_client):
    db = _db()
    html = "<h1>Site visit</h1><p><strong>Bold</strong> <em>italic</em> <u>u</u></p>" + "<p>x</p>" * 20000
    r = fin_client(db, PM).post(f"/api/v1/projects/{PROJECT['id']}/notes",
                                json={"title": " Site visit ", "content_html": html, "content_text": "Site visit"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Site visit"
    assert body["created_by_name"] == "Pat PM"
    assert body["can_edit"] is True
    assert len(db.tables["project_notes"][0]["content_html"]) == len(html)


def test_script_content_refused(fin_client):
    c = fin_client(_db(), PM)
    for bad in ("<p>a</p><script>alert(1)</script>", '<img src=x onerror="alert(1)">',
                '<a href="javascript:alert(1)">x</a>', "<iframe src=x></iframe>"):
        r = c.post(f"/api/v1/projects/{PROJECT['id']}/notes", json={"title": "t", "content_html": bad})
        assert r.status_code == 422, bad


def test_blank_title_refused(fin_client):
    r = fin_client(_db(), PM).post(f"/api/v1/projects/{PROJECT['id']}/notes", json={"title": "   "})
    assert r.status_code == 422


def test_list_newest_first_with_names(fin_client):
    a = _note(updated_at="2026-11-01T00:00:00+00:00", title="Old")
    b = _note(author=ADMIN["user_id"], updated_at="2026-11-10T00:00:00+00:00", title="New")
    deleted = _note(deleted_at=NOW, title="Gone")
    rows = fin_client(_db([a, b, deleted]), PM).get(f"/api/v1/projects/{PROJECT['id']}/notes").json()
    assert [r["title"] for r in rows] == ["New", "Old"]
    assert rows[0]["created_by_name"] == "Ada Admin"
    assert [r["can_edit"] for r in rows] == [False, True]


def test_author_edits(fin_client):
    n = _note()
    db = _db([n])
    r = fin_client(db, PM).patch(f"/api/v1/project-notes/{n['id']}",
                                 json={"content_html": "<p>Updated <strong>text</strong></p>"})
    assert r.status_code == 200, r.text
    assert db.tables["project_notes"][0]["content_html"].startswith("<p>Updated")
    assert db.tables["project_notes"][0]["updated_by"] == PM["user_id"]


def test_other_user_cannot_edit_or_delete(fin_client):
    n = _note(author=ADMIN["user_id"])
    c = fin_client(_db([n]), identity(str(uuid4())))
    assert c.patch(f"/api/v1/project-notes/{n['id']}", json={"title": "x"}).status_code == 403
    assert c.delete(f"/api/v1/project-notes/{n['id']}").status_code == 403


def test_admin_deletes_any_note_softly(fin_client):
    n = _note()
    db = _db([n])
    assert fin_client(db, ADMIN).delete(f"/api/v1/project-notes/{n['id']}").status_code == 204
    assert db.tables["project_notes"][0]["deleted_at"] is not None


def test_archived_project_is_read_only(fin_client):
    n = _note()
    c = fin_client(_db([n], {**PROJECT, "archived_at": NOW}), PM)
    assert c.get(f"/api/v1/projects/{PROJECT['id']}/notes").status_code == 200
    assert c.post(f"/api/v1/projects/{PROJECT['id']}/notes", json={"title": "x"}).status_code == 409
    assert c.patch(f"/api/v1/project-notes/{n['id']}", json={"title": "x"}).status_code == 409


def test_unknown_project_404(fin_client):
    r = fin_client(_db(), PM).get(f"/api/v1/projects/{uuid4()}/notes")
    assert r.status_code == 404
