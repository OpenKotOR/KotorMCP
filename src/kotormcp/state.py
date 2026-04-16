"""Shared state for KotorMCP: installation cache, snapshots, game aliases, path resolution."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pykotor.common.misc import Game
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff
from pykotor.resource.type import ResourceType
from pykotor.tools.model import iterate_lightmaps, iterate_textures
from pykotor.tools.path import CaseAwarePath, find_kotor_paths_from_default
from pykotor.tools.references import extract_references
from pykotor.tools.resource_json import iter_installation_resource_documents
from pykotor.tools.validation import get_installation_summary

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pykotor.tools.resource_json import JsonValue


@dataclass(frozen=True)
class InstallationSnapshotResource:
    document_path: str
    document: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        return {
            "documentPath": self.document_path,
            "resource": self.document.get("resource"),
            "resname": self.document.get("resname"),
            "restype": self.document.get("restype"),
            "extension": self.document.get("extension"),
            "sourcePath": self.document.get("source_path"),
            "containerPath": self.document.get("container_path"),
            "offset": self.document.get("offset"),
            "size": self.document.get("size"),
            "encoding": self.document.get("encoding"),
            "payloadOmitted": bool(self.document.get("payloadOmitted", False)),
            "error": self.document.get("error"),
        }


@dataclass(frozen=True)
class InstallationGraphEdge:
    source_document_path: str
    source_resource: str
    source_restype: str
    source_path: str | None
    edge_kind: str
    target_name: str
    target_restypes: tuple[str, ...]
    field_path: str | None = None
    target_document_paths: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sourceDocumentPath": self.source_document_path,
            "sourceResource": self.source_resource,
            "sourceRestype": self.source_restype,
            "edgeKind": self.edge_kind,
            "targetName": self.target_name,
            "targetRestypes": list(self.target_restypes),
            "targetResolved": bool(self.target_document_paths),
            "targetDocumentPaths": list(self.target_document_paths),
        }
        if self.source_path is not None:
            payload["sourcePath"] = self.source_path
        if self.field_path is not None:
            payload["fieldPath"] = self.field_path
        return payload


@dataclass(frozen=True)
class InstallationSnapshot:
    snapshot_id: str
    game: Game
    installation_path: str
    policy_name: str
    created_at: str
    summary: dict[str, Any]
    resources: list[InstallationSnapshotResource]
    counts_by_encoding: dict[str, int]
    counts_by_restype: dict[str, int]
    graph_edges: list[InstallationGraphEdge]
    counts_by_edge_kind: dict[str, int]
    omitted_payload_count: int
    error_count: int

    def open_payload(self, *, cached: bool) -> dict[str, Any]:
        return {
            "snapshotId": self.snapshot_id,
            "cached": cached,
            "game": self.game.name,
            "path": self.installation_path,
            "policy": self.policy_name,
            "createdAt": self.created_at,
            "summary": self.summary,
            "resourceCount": len(self.resources),
            "graphEdgeCount": len(self.graph_edges),
            "countsByEncoding": self.counts_by_encoding,
            "countsByRestype": self.counts_by_restype,
            "countsByEdgeKind": self.counts_by_edge_kind,
            "omittedPayloadCount": self.omitted_payload_count,
            "errorCount": self.error_count,
        }

    def page(
        self,
        *,
        limit: int,
        offset: int,
        include_data: bool,
        resource_types: list[str] | None = None,
        resref_query: str | None = None,
        source_query: str | None = None,
    ) -> dict[str, Any]:
        normalized_types = {item.strip().lstrip(".").upper() for item in resource_types or [] if item.strip()}
        resref_query_lower = resref_query.lower() if resref_query else None
        source_query_lower = source_query.lower() if source_query else None

        filtered: list[InstallationSnapshotResource] = []
        for resource in self.resources:
            restype = str(resource.document.get("restype", "")).upper()
            extension = str(resource.document.get("extension", "")).upper()
            if normalized_types and restype not in normalized_types and extension not in normalized_types:
                continue

            if resref_query_lower is not None:
                resource_text = " ".join(
                    str(value)
                    for value in (resource.document.get("resource"), resource.document.get("resname"))
                    if value is not None
                ).lower()
                if resref_query_lower not in resource_text:
                    continue

            if source_query_lower is not None:
                source_text = " ".join(
                    str(value)
                    for value in (
                        resource.document.get("source_path"),
                        resource.document.get("container_path"),
                    )
                    if value is not None
                ).lower()
                if source_query_lower not in source_text:
                    continue

            filtered.append(resource)

        page_items = filtered[offset : offset + limit]
        next_offset = offset + limit if (offset + limit) < len(filtered) else None
        items = [resource.document if include_data else resource.summary() for resource in page_items]
        return {
            "snapshotId": self.snapshot_id,
            "game": self.game.name,
            "path": self.installation_path,
            "policy": self.policy_name,
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "nextOffset": next_offset,
            "includeData": include_data,
            "items": items,
        }

    def page_graph(
        self,
        *,
        limit: int,
        offset: int,
        edge_kinds: list[str] | None = None,
        target_types: list[str] | None = None,
        query: str | None = None,
        source_query: str | None = None,
    ) -> dict[str, Any]:
        normalized_edge_kinds = {item.strip().lower() for item in edge_kinds or [] if item.strip()}
        normalized_target_types = {item.strip().upper() for item in target_types or [] if item.strip()}
        query_lower = query.lower() if query else None
        source_query_lower = source_query.lower() if source_query else None

        filtered: list[InstallationGraphEdge] = []
        for edge in self.graph_edges:
            if normalized_edge_kinds and edge.edge_kind not in normalized_edge_kinds:
                continue
            if normalized_target_types and not normalized_target_types.intersection(edge.target_restypes):
                continue
            if query_lower is not None:
                query_text = " ".join(
                    value
                    for value in (edge.target_name, edge.field_path or "", edge.source_resource)
                    if value
                ).lower()
                if query_lower not in query_text:
                    continue
            if source_query_lower is not None:
                source_text = " ".join(
                    value
                    for value in (edge.source_document_path, edge.source_path or "", edge.source_resource)
                    if value
                ).lower()
                if source_query_lower not in source_text:
                    continue
            filtered.append(edge)

        page_items = filtered[offset : offset + limit]
        next_offset = offset + limit if (offset + limit) < len(filtered) else None
        return {
            "snapshotId": self.snapshot_id,
            "game": self.game.name,
            "path": self.installation_path,
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "nextOffset": next_offset,
            "items": [edge.to_payload() for edge in page_items],
        }

INSTALLATIONS: dict[Game, Installation] = {}
SNAPSHOTS: dict[str, InstallationSnapshot] = {}
SNAPSHOT_CACHE_KEYS: dict[tuple[str, str, str], str] = {}
DEFAULT_PATH_CACHE = find_kotor_paths_from_default()
GAME_ALIASES: dict[str, Game] = {
    "k1": Game.K1,
    "kotori": Game.K1,
    "swkotor": Game.K1,
    "k2": Game.K2,
    "tsl": Game.K2,
    "kotor2": Game.K2,
}
ENV_HINTS: dict[Game, tuple[str, ...]] = {
    Game.K1: ("K1_PATH", "KOTOR_PATH", "KOTOR1_PATH"),
    Game.K2: ("K2_PATH", "TSL_PATH", "KOTOR2_PATH", "K1_PATH"),
}
DEFAULT_SNAPSHOT_POLICY = "default"
_SNAPSHOT_JSON_CHAR_LIMIT = 12_000
_SNAPSHOT_TEXT_CHAR_LIMIT = 6_000
_SNAPSHOT_PREVIEW_CHAR_LIMIT = 2_000
_GRAPH_REF_TARGET_TYPES: dict[str, tuple[str, ...]] = {
    "script": ("NCS", "NSS"),
    "conversation": ("DLG",),
    "template_resref": (),
}


def resolve_game(label: str | None) -> Game | None:
    """Resolve game alias (k1, k2, tsl, etc.) to Game enum."""
    if label is None:
        return None
    normalized = label.strip().lower()
    return GAME_ALIASES.get(normalized)


def iter_candidate_paths(game: Game, explicit: str | None) -> Iterator[CaseAwarePath]:
    """Yield candidate installation paths: explicit, then env vars, then defaults."""
    seen: set[str] = set()
    if explicit:
        candidate = CaseAwarePath(explicit).expanduser().resolve()
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            yield candidate
    for env_name in ENV_HINTS.get(game, ()):
        env_value = os.environ.get(env_name)
        if env_value:
            candidate = CaseAwarePath(env_value).expanduser().resolve()
            key = str(candidate).lower()
            if key not in seen:
                seen.add(key)
                yield candidate
    for default_path in DEFAULT_PATH_CACHE.get(game, []):
        key = str(default_path).lower()
        if key not in seen:
            seen.add(key)
            yield default_path


def _normalize_path(pathlike: os.PathLike[str] | str) -> str:
    return str(CaseAwarePath(pathlike).expanduser().resolve()).lower()


def _installation_matches(installation: Installation, candidate: CaseAwarePath) -> bool:
    return _normalize_path(str(installation.path())) == _normalize_path(str(candidate))


def _summarize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        keys = list(payload)
        summary = {
            "kind": "object",
            "keyCount": len(keys),
            "keys": keys[:25],
        }
        for list_key, count_key in (("rows", "rowCount"), ("strings", "stringCount"), ("newanim", "animationCount")):
            value = payload.get(list_key)
            if isinstance(value, list):
                summary[count_key] = len(value)
        return summary
    if isinstance(payload, list):
        return {"kind": "array", "itemCount": len(payload)}
    if isinstance(payload, str):
        return {"kind": "text", "charCount": len(payload)}
    return {"kind": type(payload).__name__}


def _compact_tpc_payload(payload: dict[str, Any]) -> dict[str, Any]:
    compacted = {key: value for key, value in payload.items() if key != "layers"}
    compacted_layers: list[dict[str, Any]] = []
    layers = payload.get("layers", [])
    if isinstance(layers, list):
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            compacted_layer = {key: value for key, value in layer.items() if key != "mipmaps"}
            compacted_mipmaps: list[dict[str, Any]] = []
            mipmaps = layer.get("mipmaps", [])
            if isinstance(mipmaps, list):
                for mipmap in mipmaps:
                    if not isinstance(mipmap, dict):
                        continue
                    compacted_mipmap = {
                        key: value
                        for key, value in mipmap.items()
                        if key not in {"data_hex", "data_base64"}
                    }
                    data_hex = mipmap.get("data_hex")
                    if isinstance(data_hex, str):
                        compacted_mipmap["byteCount"] = len(data_hex) // 2
                    compacted_mipmap["dataOmitted"] = True
                    compacted_mipmaps.append(compacted_mipmap)
            compacted_layer["mipmaps"] = compacted_mipmaps
            compacted_layers.append(compacted_layer)
    compacted["layers"] = compacted_layers
    return compacted


def _compact_snapshot_document(document: dict[str, JsonValue]) -> dict[str, Any]:
    compacted: dict[str, Any] = dict(document)
    if "error" in compacted:
        return compacted

    encoding = compacted.get("encoding")
    if encoding == "base64":
        compacted.pop("data_base64", None)
        compacted["payloadOmitted"] = True
        compacted["omittedReason"] = "binary_payload"
        return compacted

    data = compacted.get("data")
    if encoding == "tpc_json" and isinstance(data, dict):
        compacted["data"] = _compact_tpc_payload(data)
        compacted["payloadOmitted"] = True
        compacted["omittedReason"] = "texture_mipmap_payload"
        return compacted

    if isinstance(data, str) and len(data) > _SNAPSHOT_TEXT_CHAR_LIMIT:
        compacted.pop("data", None)
        compacted["dataPreview"] = data[:_SNAPSHOT_PREVIEW_CHAR_LIMIT]
        compacted["dataSummary"] = _summarize_payload(data)
        compacted["payloadOmitted"] = True
        compacted["omittedReason"] = "text_payload_too_large"
        return compacted

    if data is not None:
        serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) > _SNAPSHOT_JSON_CHAR_LIMIT:
            compacted.pop("data", None)
            compacted["dataPreview"] = serialized[:_SNAPSHOT_PREVIEW_CHAR_LIMIT]
            compacted["dataSummary"] = _summarize_payload(data)
            compacted["payloadOmitted"] = True
            compacted["omittedReason"] = "structured_payload_too_large"
    return compacted


def _extract_graph_edges(
    resource_document: InstallationSnapshotResource,
    resource_type: ResourceType,
    resource_data: bytes,
) -> list[InstallationGraphEdge]:
    edges: list[InstallationGraphEdge] = []
    seen: set[tuple[str, str, tuple[str, ...], str | None]] = set()
    source_restype = resource_type.extension.upper()
    source_path = resource_document.document.get("source_path")
    source_path_str = str(source_path) if isinstance(source_path, str) else None

    def add_edge(edge_kind: str, target_name: str, *, field_path: str | None = None) -> None:
        normalized_target = target_name.strip().lower()
        if not normalized_target:
            return
        target_restypes = _GRAPH_REF_TARGET_TYPES.get(edge_kind, ())
        edge_key = (edge_kind, normalized_target, target_restypes, field_path)
        if edge_key in seen:
            return
        seen.add(edge_key)
        edges.append(
            InstallationGraphEdge(
                source_document_path=resource_document.document_path,
                source_resource=str(resource_document.document.get("resource", "")),
                source_restype=source_restype,
                source_path=source_path_str,
                edge_kind=edge_kind,
                target_name=normalized_target,
                target_restypes=target_restypes,
                field_path=field_path,
            )
        )

    if source_restype == "MDL":
        try:
            for texture in iterate_textures(resource_data):
                add_edge("mdl_texture", texture)
            for lightmap in iterate_lightmaps(resource_data):
                add_edge("mdl_lightmap", lightmap)
        except Exception:
            return edges
        return edges

    if source_restype not in {"ARE", "DLG", "IFO", "UTC", "UTD", "UTI", "UTM", "UTP", "UTT"}:
        return edges

    try:
        gff = read_gff(resource_data)
    except Exception:
        return edges

    for reference in extract_references(gff, source_restype):
        if reference.ref_kind not in _GRAPH_REF_TARGET_TYPES:
            continue
        add_edge(reference.ref_kind, reference.value, field_path=reference.field_path)
    return edges


def _resolve_graph_edges(
    resources: list[InstallationSnapshotResource],
    graph_edges: list[InstallationGraphEdge],
) -> list[InstallationGraphEdge]:
    by_resname: dict[str, list[str]] = {}
    by_resname_and_type: dict[tuple[str, str], list[str]] = {}

    for resource in resources:
        resource_name = resource.document.get("resname")
        restype = resource.document.get("restype")
        if not isinstance(resource_name, str):
            continue
        resource_key = resource_name.lower()
        by_resname.setdefault(resource_key, []).append(resource.document_path)
        if isinstance(restype, str):
            by_resname_and_type.setdefault((resource_key, restype.upper()), []).append(resource.document_path)

    resolved_edges: list[InstallationGraphEdge] = []
    for edge in graph_edges:
        if edge.target_restypes:
            resolved_paths = sorted(
                {
                    path
                    for restype in edge.target_restypes
                    for path in by_resname_and_type.get((edge.target_name, restype), [])
                }
            )
        else:
            resolved_paths = sorted(set(by_resname.get(edge.target_name, [])))
        resolved_edges.append(
            InstallationGraphEdge(
                source_document_path=edge.source_document_path,
                source_resource=edge.source_resource,
                source_restype=edge.source_restype,
                source_path=edge.source_path,
                edge_kind=edge.edge_kind,
                target_name=edge.target_name,
                target_restypes=edge.target_restypes,
                field_path=edge.field_path,
                target_document_paths=tuple(resolved_paths),
            )
        )
    return resolved_edges


def _build_installation_snapshot(
    installation: Installation,
    *,
    policy_name: str,
) -> InstallationSnapshot:
    from loggerplus import RobustLogger  # noqa: PLC0415

    resources: list[InstallationSnapshotResource] = []
    counts_by_encoding: dict[str, int] = {}
    counts_by_restype: dict[str, int] = {}
    graph_edges: list[InstallationGraphEdge] = []
    counts_by_edge_kind: dict[str, int] = {}
    omitted_payload_count = 0
    error_count = 0

    for serialized_document in iter_installation_resource_documents(installation, RobustLogger()):
        compacted_document = _compact_snapshot_document(serialized_document.document)
        snapshot_resource = InstallationSnapshotResource(
            document_path=serialized_document.relative_path,
            document=compacted_document,
        )
        resources.append(snapshot_resource)

        encoding = compacted_document.get("encoding")
        if isinstance(encoding, str):
            counts_by_encoding[encoding] = counts_by_encoding.get(encoding, 0) + 1

        restype = compacted_document.get("restype")
        if isinstance(restype, str):
            counts_by_restype[restype] = counts_by_restype.get(restype, 0) + 1

        if compacted_document.get("payloadOmitted") is True:
            omitted_payload_count += 1
        if compacted_document.get("error") is not None:
            error_count += 1

        try:
            resource_type = serialized_document.resource.restype()
            resource_data = serialized_document.resource.data()
        except Exception:
            continue
        graph_edges.extend(_extract_graph_edges(snapshot_resource, resource_type, resource_data))

    resolved_graph_edges = _resolve_graph_edges(resources, graph_edges)
    for edge in resolved_graph_edges:
        counts_by_edge_kind[edge.edge_kind] = counts_by_edge_kind.get(edge.edge_kind, 0) + 1

    return InstallationSnapshot(
        snapshot_id=uuid4().hex,
        game=installation.game(),
        installation_path=str(installation.path()),
        policy_name=policy_name,
        created_at=datetime.now(UTC).isoformat(),
        summary=_safe_installation_summary(installation),
        resources=resources,
        counts_by_encoding=counts_by_encoding,
        counts_by_restype=counts_by_restype,
        graph_edges=resolved_graph_edges,
        counts_by_edge_kind=counts_by_edge_kind,
        omitted_payload_count=omitted_payload_count,
        error_count=error_count,
    )


def _safe_installation_summary(installation: Installation) -> dict[str, Any]:
    try:
        return get_installation_summary(installation)
    except Exception as exc:
        module_count = 0
        override_file_count = 0
        try:
            module_count = len(installation.modules_list())
        except Exception:
            module_count = 0
        try:
            override_file_count = sum(1 for _ in installation.override_resources())
        except Exception:
            override_file_count = 0
        return {
            "path": str(installation.path()),
            "game": installation.game().name,
            "valid": False,
            "errors": [f"Snapshot summary fallback: {exc.__class__.__name__}: {exc}"],
            "missing": [],
            "module_count": module_count,
            "override_file_count": override_file_count,
        }


def open_installation_snapshot(
    game: Game,
    explicit_path: str | None = None,
    *,
    refresh: bool = False,
    policy_name: str = DEFAULT_SNAPSHOT_POLICY,
) -> tuple[InstallationSnapshot, bool]:
    installation = load_installation(game, explicit_path)
    cache_key = (game.name, _normalize_path(str(installation.path())), policy_name)
    cached_snapshot_id = SNAPSHOT_CACHE_KEYS.get(cache_key)
    if cached_snapshot_id is not None and not refresh:
        cached_snapshot = SNAPSHOTS.get(cached_snapshot_id)
        if cached_snapshot is not None:
            return cached_snapshot, False

    snapshot = _build_installation_snapshot(installation, policy_name=policy_name)
    if cached_snapshot_id is not None:
        SNAPSHOTS.pop(cached_snapshot_id, None)
    SNAPSHOTS[snapshot.snapshot_id] = snapshot
    SNAPSHOT_CACHE_KEYS[cache_key] = snapshot.snapshot_id
    return snapshot, True


def get_installation_snapshot(snapshot_id: str) -> InstallationSnapshot:
    snapshot = SNAPSHOTS.get(snapshot_id)
    if snapshot is None:
        msg = f"Unknown installation snapshot '{snapshot_id}'. Call openInstallation first."
        raise ValueError(msg)
    return snapshot


def load_installation(game: Game, explicit_path: str | None = None) -> Installation:
    """Load and cache an installation for the given game."""
    cached = INSTALLATIONS.get(game)

    for candidate in iter_candidate_paths(game, explicit_path):
        if candidate.is_dir():
            if cached is not None and _installation_matches(cached, candidate):
                return cached
            INSTALLATIONS[game] = Installation(candidate)
            return INSTALLATIONS[game]

    msg = f"Unable to locate installation for {game.name}. Provide --path or set {ENV_HINTS[game][0]}."
    raise ValueError(msg)
