"""
Identity & Security Diagnostic Tool.
Run when auth issues are reported to identify root cause.

Usage: python diagnose.py [--base-url https://127.0.0.1:8000]
"""
import asyncio
import sys
import httpx

async def diagnose(base_url: str = "https://127.0.0.1:8000"):
    results = []

    async with httpx.AsyncClient(base_url=base_url, verify=False) as client:
        # Check 1: Backend reachable
        try:
            r = await client.get("/api/v1/health")
            results.append(("Backend reachable", r.status_code == 200, f"status={r.status_code}"))
        except Exception as e:
            results.append(("Backend reachable", False, str(e)))

        # Check 2: Auth endpoints registered
        try:
            r = await client.get("/api/v1/auth/login", follow_redirects=False)
            results.append(("Auth login route", r.status_code in (302, 307, 400), f"status={r.status_code}"))
        except Exception as e:
            results.append(("Auth login route", False, str(e)))

        # Check 3: /me endpoint exists
        try:
            r = await client.get("/api/v1/auth/me")
            results.append(("Auth me route", r.status_code in (200, 401), f"status={r.status_code}"))
        except Exception as e:
            results.append(("Auth me route", False, str(e)))

        # Check 4: Session status endpoint
        try:
            r = await client.get("/api/v1/auth/session/status")
            results.append(("Session status route", r.status_code == 200, f"status={r.status_code}"))
        except Exception as e:
            results.append(("Session status route", False, str(e)))

        # Check 5: Entra token endpoint reachable
        try:
            r = await client.get("https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration")
            results.append(("Entra reachable", r.status_code == 200, ""))
        except Exception as e:
            results.append(("Entra reachable", False, str(e)))

        # Check 6: Login redirect URL well-formed
        try:
            r = await client.get("/api/v1/auth/login", follow_redirects=False)
            loc = r.headers.get("location", "")
            has_client_id = "client_id=" in loc
            has_redirect = "redirect_uri=" in loc
            has_pkce = "code_challenge=" in loc
            ok = has_client_id and has_redirect and has_pkce
            detail = f"client_id={'Y' if has_client_id else 'N'} redirect_uri={'Y' if has_redirect else 'N'} PKCE={'Y' if has_pkce else 'N'}"
            results.append(("Login URL well-formed", ok, detail))
        except Exception as e:
            results.append(("Login URL well-formed", False, str(e)))

    # Print results
    print("\n" + "=" * 60)
    print("IDENTITY & SECURITY DIAGNOSTIC REPORT")
    print("=" * 60)

    all_pass = True
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        detail_str = f"  ({detail})" if detail else ""
        print(f"  [{status}] {name}{detail_str}")

    print("=" * 60)
    print(f"Result: {'ALL CHECKS PASSED' if all_pass else 'FAILURES DETECTED'}")
    print("=" * 60 + "\n")

    return 0 if all_pass else 1

if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "https://127.0.0.1:8000"
    exit_code = asyncio.run(diagnose(base))
    sys.exit(exit_code)
