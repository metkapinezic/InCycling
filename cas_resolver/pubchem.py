## PubChem API client ##

from __future__ import annotations # fixes the Python 3.9 type hint issue. Without this, writing list[str] as a type hint crashes on 3.9.

import asyncio
import logging
import re
from typing import Optional

import httpx # Why httpx and not requests? requests is synchronous — it blocks while waiting for a response. We want to send multiple API calls concurrently (async), and httpx supports that natively with the same friendly API.

logger = logging.getLogger(__name__) # this creates a logger named after the current file (cas_resolver.pubchem). It means when a log message appears, you know exactly which file it came from.

_CAS_PATTERN = re.compile(r"^\d{1,7}-\d{2}-\d$") # the regex that identifies a CAS number. The ^ and $ anchor it to the full string (so 67-64-1-extra won't match). The underscores prefix means "private to this module — don't import this from outside".

PUBCHEM_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

_RATE_LIMIT_DELAY = 0.2 # PubChem's public API allows about 5 requests per second for anonymous users. 0.2 seconds between requests = 5/second. If you hammer it faster, they'll block you with a 429 error.
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0 # if a request fails, we wait 2 seconds before retry 1, 4 seconds before retry 2, 8 before retry 3. This is called exponential backoff — standard practice for any production API client.


# step [1]#

# PubChem doesn't have a dedicated "CAS number" field. 
# Instead it returns a long list of synonyms for a compound — common names, trade names, identifiers from other databases, and buried in there, usually a CAS number. 
# This function loops through that list and returns the first string that looks like a CAS number.
def _extract_cas(synonyms: list[str]) -> Optional[str]:
    """Return the first CAS-formatted string from a list of synonyms, or None."""
    for syn in synonyms:
        if _CAS_PATTERN.match(syn.strip()):
            return syn.strip() # we strip whitespace just in case the CAS number is padded with spaces.
    return None # Why return None and not raise an error? Because "no CAS found" is a normal, expected outcome — not a bug. Mixtures, proprietary products, and typos won't have CAS numbers. Raising an exception would crash the whole pipeline for something that should just produce a NOT FOUND row.


#step[2] #

async def resolve_cas(  # defines a function that can be paused and resumed. You can't call it like a normal function.#
    name: str,
    client: httpx.AsyncClient, # we pass the client in rather than creating a new one each call. One client = one connection pool shared across all requests. Much more efficient.
    semaphore: asyncio.Semaphore, #  a semaphore is a counter that limits concurrency. If we create Semaphore(5), only 5 requests can run simultaneously. Without this, we'd fire all 30 requests at once and PubChem would block us.
) -> Optional[str]:
    """
    Resolve a single chemical name to its CAS Registry Number via PubChem.
    """
    url = f"{PUBCHEM_BASE_URL}/compound/name/{httpx.URL(name)}/synonyms/JSON" # Chemical names can contain spaces and special characters. httpx.URL(name) properly URL-encodes them — "Isopropyl alcohol" becomes "Isopropyl%20alcohol" in the URL.

    async with semaphore:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.get(url) # await means "pause here and wait for this to finish, but let other things run in the meantime". You can only use await inside an async def.#


                if response.status_code == 404: # compound not found — this is expected for some inputs, return None quietly
                    logger.warning("PubChem: no compound found for %r", name)
                    return None

                if response.status_code in (429, 503): # rate limited — this is temporary, worth retrying after a wait
                    wait = _RETRY_BACKOFF ** attempt
                    logger.warning("Rate limit hit for %r — retrying in %.1fs", name, wait)
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status() # for any other HTTP error (500, 503, etc), we log it and return None. These errors are less likely to be transient, so we don't retry.

                data = response.json()
                synonyms: list[str] = (
                    data.get("InformationList", {})
                    .get("Information", [{}])[0]
                    .get("Synonym", [])
                )
                cas = _extract_cas(synonyms)

                if cas is None:
                    logger.warning("No CAS synonym found for %r", name)
                return cas

            except httpx.TimeoutException:
                wait = _RETRY_BACKOFF ** attempt
                logger.warning("Timeout for %r (attempt %d/%d) — retrying in %.1fs",
                               name, attempt, _MAX_RETRIES, wait)
                await asyncio.sleep(wait) 
            except httpx.HTTPStatusError as exc:
                logger.error("HTTP error resolving %r: %s", name, exc)
                return None

        logger.error("Failed to resolve %r after %d attempts", name, _MAX_RETRIES)
        return None

  
# step [3] - final function, which ties it all together


async def resolve_cas_batch( # Creates one shared client and one semaphore, then fires off a task for every chemical name using asyncio.create_task. 
    names: list[str],
    max_concurrency: int = 5,
) -> dict[str, Optional[str]]:
    """
    Resolve a list of chemical names concurrently, returning a name→CAS mapping.
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    results: dict[str, Optional[str]] = {}

    async with httpx.AsyncClient(timeout=30.0) as client: # Tasks start running immediately in the background. Then we loop through and await each one to collect results.
        tasks = {
            name: asyncio.create_task(resolve_cas(name, client, semaphore))
            for name in names
        }
        for name, task in tasks.items():
            results[name] = await task
            await asyncio.sleep(_RATE_LIMIT_DELAY) # adds a small 0.2s pause between collecting each result, which smooths out the request timing.

    return results   