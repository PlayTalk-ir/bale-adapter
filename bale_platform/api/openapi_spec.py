"""OpenAPI 3.0 description of the Bale adapter HTTP API."""

from __future__ import annotations

from typing import Any, Dict


def build_openapi(base_url: str = "/") -> Dict[str, Any]:
    """Return the OpenAPI document. ``base_url`` is used for server URL in UI."""
    server = base_url.rstrip("/") or "/"
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Bale adapter HTTP API",
            "version": "1.0.0",
            "description": (
                "Queue outbound Bale messages via the PlayTalk support userbot. "
                "All endpoints except `/healthz` require a Bearer token from "
                "`BALE_ADAPTER_API_TOKENS`."
            ),
        },
        "servers": [{"url": server}],
        "tags": [
            {"name": "health"},
            {"name": "messages"},
            {"name": "admin"},
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Token from BALE_ADAPTER_API_TOKENS",
                }
            },
            "schemas": {
                "ErrorBody": {
                    "type": "object",
                    "properties": {
                        "error": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "message": {"type": "string"},
                                "details": {"type": "object"},
                            },
                            "required": ["code", "message", "details"],
                        }
                    },
                    "required": ["error"],
                },
                "RecipientPhone": {
                    "type": "object",
                    "properties": {"phone": {"type": "string", "example": "09924466793"}},
                    "required": ["phone"],
                },
                "RecipientUserId": {
                    "type": "object",
                    "properties": {"bale_user_id": {"type": "string", "example": "42"}},
                    "required": ["bale_user_id"],
                },
                "RecipientUsername": {
                    "type": "object",
                    "properties": {"username": {"type": "string", "example": "playtalk"}},
                    "required": ["username"],
                },
                "PostMessageRequest": {
                    "type": "object",
                    "properties": {
                        "recipient": {
                            "oneOf": [
                                {"$ref": "#/components/schemas/RecipientPhone"},
                                {"$ref": "#/components/schemas/RecipientUserId"},
                                {"$ref": "#/components/schemas/RecipientUsername"},
                            ],
                            "description": "Single recipient (use this or recipients, not both)",
                        },
                        "recipients": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 50,
                            "items": {
                                "oneOf": [
                                    {"$ref": "#/components/schemas/RecipientPhone"},
                                    {"$ref": "#/components/schemas/RecipientUserId"},
                                    {"$ref": "#/components/schemas/RecipientUsername"},
                                ]
                            },
                            "description": "Multiple recipients; same text/meta/TTL for each",
                        },
                        "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "idempotency_key": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9:_.-]{1,128}$",
                            "example": "rule_bale:12:34",
                            "description": "Your stable id for this send; see API docs",
                        },
                        "meta": {
                            "type": "object",
                            "description": "Optional caller metadata (≤2KB). Stored in outbox only; never sent to Bale.",
                        },
                        "ttl_seconds": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 604800,
                            "description": "Default BALE_DEFAULT_TTL_S (86400), max 7 days",
                        },
                    },
                    "required": ["text", "idempotency_key"],
                },
                "PostMessageBatchResponse": {
                    "type": "object",
                    "properties": {
                        "idempotency_key": {"type": "string"},
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "message_id": {"type": "string"},
                                    "status": {"type": "string"},
                                    "idempotency_key": {"type": "string"},
                                    "recipient": {"type": "object"},
                                },
                            },
                        },
                    },
                },
                "PostMessageResponse": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string"},
                        "status": {"type": "string", "enum": ["queued"]},
                        "idempotency_key": {"type": "string"},
                    },
                },
                "MessageStatus": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": [
                                "queued",
                                "resolving",
                                "sending",
                                "sent",
                                "failed",
                                "expired",
                                "cancelled",
                                "delivery_unknown",
                            ],
                        },
                        "attempts": {"type": "integer"},
                        "recipient": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "masked": {"type": "string"},
                            },
                        },
                        "bale_user_id": {"type": "integer", "nullable": True},
                        "bale_message_id": {"type": "integer", "nullable": True},
                        "error": {
                            "type": "object",
                            "nullable": True,
                            "properties": {
                                "code": {"type": "string"},
                                "message": {"type": "string"},
                            },
                        },
                        "dry_run": {"type": "boolean"},
                        "created_at": {"type": "string", "format": "date-time", "nullable": True},
                        "sent_at": {"type": "string", "format": "date-time", "nullable": True},
                        "updated_at": {"type": "string", "format": "date-time", "nullable": True},
                    },
                },
                "ReadyzResponse": {
                    "type": "object",
                    "properties": {
                        "session_connected": {"type": "boolean"},
                        "session_reason": {"type": "string"},
                        "queue_depth": {"type": "integer"},
                        "paused": {"type": "boolean"},
                        "send_mode": {"type": "string", "enum": ["live", "dry_run", "resolve_only"]},
                    },
                },
            },
        },
        "paths": {
            "/healthz": {
                "get": {
                    "tags": ["health"],
                    "summary": "Liveness probe",
                    "security": [],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"ok": {"type": "boolean"}},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/readyz": {
                "get": {
                    "tags": ["health"],
                    "summary": "Readiness and queue stats",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ReadyzResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorBody"}}},
                        },
                    },
                }
            },
            "/v1/messages": {
                "post": {
                    "tags": ["messages"],
                    "summary": "Queue a message",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/PostMessageRequest"}
                            }
                        },
                    },
                    "responses": {
                        "202": {
                            "description": "New message queued (single recipient) or batch queued",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "oneOf": [
                                            {"$ref": "#/components/schemas/PostMessageResponse"},
                                            {"$ref": "#/components/schemas/PostMessageBatchResponse"},
                                        ]
                                    }
                                }
                            },
                        },
                        "200": {
                            "description": "Idempotent replay (same key and payload)",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PostMessageResponse"}
                                }
                            },
                        },
                        "401": {"description": "Unauthorized"},
                        "409": {"description": "Idempotency conflict"},
                        "413": {"description": "Text too long"},
                        "422": {"description": "Validation error"},
                        "429": {"description": "Rate limited"},
                        "503": {"description": "Sending paused"},
                    },
                },
                "get": {
                    "tags": ["messages"],
                    "summary": "Lookup by idempotency key",
                    "parameters": [
                        {
                            "name": "idempotency_key",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Message status",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/MessageStatus"}
                                }
                            },
                        },
                        "401": {"description": "Unauthorized"},
                        "404": {"description": "Not found"},
                    },
                },
            },
            "/v1/messages/{message_id}": {
                "get": {
                    "tags": ["messages"],
                    "summary": "Get message status by ID",
                    "parameters": [
                        {
                            "name": "message_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Message status",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/MessageStatus"}
                                }
                            },
                        },
                        "401": {"description": "Unauthorized"},
                        "404": {"description": "Not found"},
                    },
                }
            },
            "/v1/admin/resume": {
                "post": {
                    "tags": ["admin"],
                    "summary": "Clear circuit breaker",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"ok": {"type": "boolean"}},
                                    }
                                }
                            },
                        },
                        "401": {"description": "Unauthorized"},
                    },
                }
            },
        },
        "security": [{"bearerAuth": []}],
    }
