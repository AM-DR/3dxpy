"""
3DEXPERIENCE Platform Web & REST Client (ENOVIA / 3DSpace / 3DPassport / 3DSearch / 3DSwym).

Built exclusively on the Python standard library (``urllib.request`` + ``http.cookiejar``)
so zero external HTTP packages are required.

Supports:
- **3DPassport CAS Authentication** (login ticket ``lt`` exchange + service redirect),
  **Bearer / API Key / OAuth2 tokens**, **HTTP Basic**, and **Session Cookies**.
- Automatic **CSRF token** retrieval (``/resources/v1/application/CSRF`` -> ``ENO_CSRF_TOKEN``).
- Automatic or explicit **SecurityContext** header management (``Role.Organization.CollabSpace``)
  including auto-discovery via ``/resources/modeler/pno/person?current=true``.
- **3DSpace Engineering Items (``dseng:EngItem``)**: search, read, create, update, delete, BOM expand.
- **Documents**, **Lifecycle / Maturity transitions (``dslc``)**, and **Change Actions**.
- **3DSearch (Federated Search)** and **3DSwym** community posts.
"""
from __future__ import annotations

import base64
import http.cookiejar
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping, Sequence


class PlatformAPIError(RuntimeError):
    """Raised when a 3DEXPERIENCE Platform REST call returns an HTTP error status."""

    def __init__(self, status_code: int, url: str, body: str):
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"3DEXPERIENCE HTTP {status_code} for {url}: {body[:500]}")


TransportCallable = Callable[[urllib.request.Request, float], tuple[int, Mapping[str, str], bytes]]


class ThreeDXPlatformClient:
    """
    Client for 3DEXPERIENCE Cloud & On-Premise REST Services
    (3DSpace / ENOVIA, 3DPassport, 3DSearch, 3DSwym).

    Example::

        client = ThreeDXPlatformClient(
            space_url="https://r1132100000000-eu1-space.3dexperience.3ds.com/enovia",
            passport_url="https://eu1-authn.3dexperience.3ds.com",
            security_context="VPLMProjectLeader.Company Name.Common Space",
        )
        client.set_api_token("MY_AGENT_KEY")
        items = client.search_engineering_items("Bracket")
    """

    def __init__(
        self,
        space_url: str,
        *,
        passport_url: str | None = None,
        search_url: str | None = None,
        swym_url: str | None = None,
        security_context: str | None = None,
        tenant: str | None = None,
        verify_ssl: bool = True,
        timeout: float = 30.0,
        transport: TransportCallable | None = None,
    ):
        self.space_url = space_url.rstrip("/")
        self.passport_url = passport_url.rstrip("/") if passport_url else None
        self.search_url = search_url.rstrip("/") if search_url else None
        self.swym_url = swym_url.rstrip("/") if swym_url else None
        self.security_context = security_context
        self.tenant = tenant
        self.timeout = timeout

        self.cookie_jar = http.cookiejar.CookieJar()
        self._default_headers: dict[str, str] = {"Accept": "application/json"}
        self._csrf_token: str | None = None

        ssl_ctx = ssl.create_default_context()
        if not verify_ssl:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPSHandler(context=ssl_ctx),
        )
        self._transport = transport

    # ------------------------------------------------------------------
    # Authentication Configuration
    # ------------------------------------------------------------------
    def set_api_token(
        self,
        token: str,
        *,
        header_name: str = "Authorization",
        prefix: str = "Bearer ",
    ) -> ThreeDXPlatformClient:
        """Configure Bearer / OAuth2 / Personal Access / Agent API token authentication."""
        self._default_headers[header_name] = f"{prefix}{token}" if prefix else token
        return self

    def set_basic_auth(self, username: str, password: str) -> ThreeDXPlatformClient:
        """Configure HTTP Basic authentication (e.g. Cloud Platform Agent credentials)."""
        raw = f"{username}:{password}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        self._default_headers["Authorization"] = f"Basic {encoded}"
        return self

    def set_cookies(self, cookies: Mapping[str, str], domain: str = "") -> ThreeDXPlatformClient:
        """Seed session cookies (such as ``CASTGC`` or ``JSESSIONID``)."""
        parsed_host = domain or (urllib.parse.urlparse(self.space_url).hostname or "localhost")
        for name, value in cookies.items():
            cookie = http.cookiejar.Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=parsed_host,
                domain_specified=bool(parsed_host),
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
            )
            self.cookie_jar.set_cookie(cookie)
        return self

    def login_3dpassport(
        self,
        username: str,
        password: str,
        *,
        passport_url: str | None = None,
        remember_me: bool = False,
    ) -> dict[str, Any]:
        """
        Authenticate interactively against **3DPassport** CAS:
        1. ``GET <passport>/login?action=get_auth_params`` -> extracts ``lt`` login ticket.
        2. ``POST <passport>/login`` with ``lt``, ``username``, ``password``, ``service=<space_url>``.
        """
        p_url = (passport_url or self.passport_url or "").rstrip("/")
        if not p_url:
            raise ValueError("passport_url is required for login_3dpassport().")

        auth_params = self.request(
            "GET",
            f"{p_url}/login",
            params={"action": "get_auth_params"},
            include_security_context=False,
        )
        lt_ticket = auth_params.get("lt") if isinstance(auth_params, Mapping) else None
        if not lt_ticket:
            raise RuntimeError(f"3DPassport did not return login ticket 'lt': {auth_params!r}")

        form_body = urllib.parse.urlencode({
            "lt": lt_ticket,
            "username": username,
            "password": password,
            "rememberMe": "true" if remember_me else "false",
        }).encode("utf-8")

        service_target = self.space_url
        if self.tenant:
            service_target = f"{service_target}?tenant={urllib.parse.quote(self.tenant)}"

        login_url = f"{p_url}/login?service={urllib.parse.quote(service_target, safe='')}"
        res = self.request(
            "POST",
            login_url,
            raw_body=form_body,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            include_security_context=False,
        )
        self._csrf_token = None
        return res if isinstance(res, dict) else {"authenticated": True, "response": res}

    # ------------------------------------------------------------------
    # Low-level HTTP + CSRF + SecurityContext Handling
    # ------------------------------------------------------------------
    def _build_url(
        self,
        path_or_url: str,
        params: Mapping[str, Any] | None = None,
        *,
        base_url: str | None = None,
    ) -> str:
        if path_or_url.startswith(("http://", "https://")):
            url = path_or_url
        else:
            root = (base_url or self.space_url).rstrip("/")
            rel = path_or_url if path_or_url.startswith("/") else f"/{path_or_url}"
            url = f"{root}{rel}"

        query_dict: dict[str, Any] = {}
        if self.tenant and "tenant=" not in url:
            query_dict["tenant"] = self.tenant
        if params:
            for k, v in params.items():
                if v is not None:
                    query_dict[k] = v

        if query_dict:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode(query_dict, doseq=True)}"
        return url

    def _execute_request(self, req: urllib.request.Request) -> tuple[int, Mapping[str, str], bytes]:
        if self._transport is not None:
            return self._transport(req, self.timeout)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                status = int(getattr(resp, "status", 200))
                headers = dict(resp.headers.items())
                data = resp.read()
                return status, headers, data
        except urllib.error.HTTPError as err:
            body_bytes = err.read() if err.fp is not None else b""
            raise PlatformAPIError(
                err.code,
                req.full_url,
                body_bytes.decode("utf-8", errors="replace"),
            ) from err

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        raw_body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        include_csrf: bool = False,
        include_security_context: bool = True,
        base_url: str | None = None,
    ) -> Any:
        """Perform an authenticated HTTP request against a 3DEXPERIENCE service."""
        url = self._build_url(path_or_url, params=params, base_url=base_url)
        merged_headers = dict(self._default_headers)
        if include_security_context and self.security_context:
            merged_headers.setdefault("SecurityContext", self.security_context)
        if include_csrf:
            token = self.get_csrf_token()
            merged_headers["ENO_CSRF_TOKEN"] = token
        if headers:
            merged_headers.update(headers)

        payload_bytes = raw_body
        if json_body is not None:
            payload_bytes = json.dumps(json_body).encode("utf-8")
            merged_headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(
            url=url,
            data=payload_bytes,
            headers=merged_headers,
            method=method.upper(),
        )
        status, _, resp_bytes = self._execute_request(req)
        if status >= 400:
            raise PlatformAPIError(status, url, resp_bytes.decode("utf-8", errors="replace"))
        if not resp_bytes:
            return {}
        text = resp_bytes.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def get_csrf_token(self, *, force_refresh: bool = False) -> str:
        """Fetch and cache ``ENO_CSRF_TOKEN`` from 3DSpace."""
        if self._csrf_token and not force_refresh:
            return self._csrf_token
        resp = self.request("GET", "/resources/v1/application/CSRF", include_csrf=False)
        csrf_obj = resp.get("csrf", {}) if isinstance(resp, Mapping) else {}
        token = csrf_obj.get("value")
        if not token:
            raise RuntimeError(f"Could not extract ENO_CSRF_TOKEN from response: {resp!r}")
        self._csrf_token = str(token)
        return self._csrf_token

    def discover_security_contexts(self, *, set_preferred: bool = True) -> list[str]:
        """
        Query ``/resources/modeler/pno/person?current=true`` to discover all valid
        ``Role.Organization.CollabSpace`` security contexts granted to the user.
        """
        resp = self.request(
            "GET",
            "/resources/modeler/pno/person",
            params={
                "current": "true",
                "select": ["preferredcredentials", "collabspaces"],
            },
            include_security_context=False,
        )
        contexts: list[str] = []
        if isinstance(resp, Mapping):
            pref = resp.get("preferredcredentials") or {}
            p_role = (pref.get("role") or {}).get("name")
            p_org = (pref.get("organization") or {}).get("name")
            p_cs = (pref.get("collabspace") or {}).get("name")
            if p_role and p_org and p_cs:
                preferred_ctx = f"{p_role}.{p_org}.{p_cs}"
                contexts.append(preferred_ctx)
                if set_preferred and not self.security_context:
                    self.security_context = preferred_ctx

            for cs in resp.get("collabspaces") or []:
                cs_name = cs.get("name")
                for couple in cs.get("couples") or []:
                    role_name = (couple.get("role") or {}).get("name")
                    org_name = (couple.get("organization") or {}).get("name")
                    if role_name and org_name and cs_name:
                        ctx = f"{role_name}.{org_name}.{cs_name}"
                        if ctx not in contexts:
                            contexts.append(ctx)
        return contexts

    # ------------------------------------------------------------------
    # 3DSpace: Engineering Items (dseng:EngItem) / Physical Products / BOM
    # ------------------------------------------------------------------
    def search_engineering_items(
        self,
        search_str: str,
        *,
        top: int = 50,
        skip: int = 0,
    ) -> dict[str, Any]:
        """Search Physical Products / Engineering Items in 3DSpace."""
        return self.request(
            "GET",
            "/resources/v1/modeler/dseng/dseng:EngItem/search",
            params={"$searchStr": search_str, "$top": top, "$skip": skip},
        )

    def get_engineering_item(self, item_id: str, *, mask: str = "dsmveng:EngItemMask.Details") -> dict[str, Any]:
        """Retrieve details of an Engineering Item (``VPMReference``) by physical ID."""
        return self.request(
            "GET",
            f"/resources/v1/modeler/dseng/dseng:EngItem/{urllib.parse.quote(item_id)}",
            params={"$mask": mask},
        )

    def create_engineering_item(
        self,
        title: str,
        *,
        description: str = "",
        attributes: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new Engineering Item (Physical Product) in 3DSpace."""
        item_attrs: dict[str, Any] = {"title": title, "description": description}
        if attributes:
            item_attrs.update(attributes)
        payload = {"items": [{"attributes": item_attrs}]}
        return self.request(
            "POST",
            "/resources/v1/modeler/dseng/dseng:EngItem",
            json_body=payload,
            include_csrf=True,
        )

    def update_engineering_item(self, item_id: str, attributes: Mapping[str, Any]) -> dict[str, Any]:
        """Update attributes on an existing Engineering Item."""
        return self.request(
            "PATCH",
            f"/resources/v1/modeler/dseng/dseng:EngItem/{urllib.parse.quote(item_id)}",
            json_body=dict(attributes),
            include_csrf=True,
        )

    def delete_engineering_item(self, item_id: str) -> dict[str, Any]:
        """Delete an Engineering Item by ID."""
        return self.request(
            "DELETE",
            f"/resources/v1/modeler/dseng/dseng:EngItem/{urllib.parse.quote(item_id)}",
            include_csrf=True,
        )

    def expand_engineering_item(
        self,
        item_id: str,
        *,
        expand_depth: int = 1,
        with_instances: bool = True,
    ) -> dict[str, Any]:
        """Expand the product structure / BOM of an Engineering Item."""
        body = {
            "expandDepth": int(expand_depth),
            "withPath": True,
            "type_filter_bo": ["VPMReference"],
            "type_filter_rel": ["VPMInstance"] if with_instances else [],
        }
        return self.request(
            "POST",
            f"/resources/v1/modeler/dseng/dseng:EngItem/{urllib.parse.quote(item_id)}/expand",
            json_body=body,
            include_csrf=True,
        )

    # ------------------------------------------------------------------
    # Documents, Lifecycle (dslc), & Change Actions (dslc:changeaction)
    # ------------------------------------------------------------------
    def get_document(self, document_id: str) -> dict[str, Any]:
        """Fetch a PLM Document and its attached files metadata."""
        return self.request("GET", f"/resources/v1/modeler/documents/{urllib.parse.quote(document_id)}")

    def create_document(self, title: str, *, description: str = "") -> dict[str, Any]:
        """Create a new PLM Document container in 3DSpace."""
        payload = {
            "data": [
                {
                    "tempId": "doc_1",
                    "dataelements": {"title": title, "description": description},
                }
            ]
        }
        return self.request(
            "POST",
            "/resources/v1/modeler/documents",
            json_body=payload,
            include_csrf=True,
        )

    def set_maturity_state(self, object_id: str, target_state: str) -> dict[str, Any]:
        """
        Transition an object's Collaborative Lifecycle maturity state
        (e.g. ``'IN_WORK'``, ``'FROZEN'``, ``'RELEASED'``, ``'OBSOLETE'``).
        """
        payload = {"data": [{"id": object_id, "nextState": target_state}]}
        return self.request(
            "POST",
            "/resources/v1/modeler/dslc/maturity/changeState",
            json_body=payload,
            include_csrf=True,
        )

    def get_change_action(self, change_action_id: str) -> dict[str, Any]:
        """Retrieve an ENOVIA Change Action by ID."""
        return self.request(
            "GET",
            f"/resources/v1/modeler/dslc/changeaction/{urllib.parse.quote(change_action_id)}",
        )

    def create_change_action(
        self,
        title: str,
        *,
        description: str = "",
        severity: str = "Low",
    ) -> dict[str, Any]:
        """Create an ENOVIA Change Action."""
        return self.request(
            "POST",
            "/resources/v1/modeler/dslc/changeaction",
            json_body={"title": title, "description": description, "severity": severity},
            include_csrf=True,
        )

    # ------------------------------------------------------------------
    # 3DSearch (Federated Search) & 3DSwym
    # ------------------------------------------------------------------
    def federated_search(
        self,
        query: str,
        *,
        max_results: int = 50,
        sources: Sequence[str] = ("3dspace",),
    ) -> dict[str, Any]:
        """Query **3DSearch** (``/federated/search``) across 3DEXPERIENCE data sources."""
        if not self.search_url:
            raise ValueError("search_url must be provided on ThreeDXPlatformClient for federated_search().")
        body = {
            "query": query,
            "nresults": int(max_results),
            "source": list(sources),
            "with_synthesis": True,
        }
        if self.tenant:
            body["tenant"] = self.tenant
        return self.request(
            "POST",
            "/search",
            json_body=body,
            base_url=self.search_url,
            include_security_context=False,
        )

    def list_swym_communities(self, *, page: int = 1, limit: int = 25) -> dict[str, Any]:
        """List **3DSwym** communities accessible to the authenticated user."""
        if not self.swym_url:
            raise ValueError("swym_url must be provided on ThreeDXPlatformClient for 3DSwym calls.")
        return self.request(
            "GET",
            "/api/community/listmycommunities",
            params={"page": page, "limit": limit},
            base_url=self.swym_url,
            include_security_context=False,
        )


EnoviaClient = ThreeDXPlatformClient
