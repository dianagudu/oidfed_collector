# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

from typing import Literal
from pydantic import BaseModel, ConfigDict
import urllib.parse
import time
from pydantic import HttpUrl
import pydantic_core
import logging
import json
from cryptojwt.jws.jws import factory

from .message import EntityStatement
from .exceptions import InternalException

logger = logging.getLogger(__name__)


EntityType = Literal[
    "openid_provider",
    "openid_relying_party",
    "oauth_authorization_server",
    "oauth_client",
    "oauth_resource",
    "federation_entity",
]

EntityClaims = Literal[
    "entity_id",
    "entity_types",
    "trust_marks",
    "ui_infos",
]

UiClaims = Literal[
    "display_name",
    "description",
    "keywords",
    "logo_uri",
    "policy_uri",
    "information_uri",
]


class EntityCollectionRequest(BaseModel):
    """Request for entity collection"""

    model_config = ConfigDict(extra="forbid")

    from_entity_id: HttpUrl | None = None
    limit: int | None = None
    entity_type: list[EntityType] | None = None
    trust_mark_type: list[str] | None = None
    trust_anchor: HttpUrl
    # query: str | None = None
    entity_claims: list[EntityClaims] | None = None
    ui_claims: list[UiClaims] | None = None
    lang: str | None = None


class UiInfo(BaseModel):
    """UI information for an entity"""

    display_name: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    logo_uri: HttpUrl | str | None = None
    policy_uri: HttpUrl | str | None = None
    information_uri: HttpUrl | str | None = None

    # this is to allow language tags in the UI info for all claims
    class Config:
        extra = "allow"

    # function that can filter based on language, where additional fields are named field#lang
    # e.g. display_name#en, display_name#fr, etc.
    # by default, when lang is not specified, all language tags are returned
    # when lang is specified, the fields without the language tag is returned,
    # as well as the fields with the requested language tag
    # all other language tagged fields are filtered out
    def to_dict(self, lang: str | None = None):
        data = self.model_dump(exclude_none=True, exclude_unset=True)
        if lang:
            # filter fields with language tag
            for key in list(data.keys()):
                if key.endswith(f"#{lang}"):
                    pass  # keep the language tagged field
                elif "#" in key:
                    # remove all other language tagged fields
                    data.pop(key, None)
        return data


class Entity(BaseModel):
    """Entity"""

    entity_id: HttpUrl
    entity_types: list[EntityType] | None = None
    ui_infos: dict[EntityType, UiInfo] | None = None
    trust_marks: list[dict[Literal["trust_mark_type", "trust_mark"], str]] | None = None

    def to_dict(self, lang: str | None = None):
        # apply to_dict on ui_infos if they are UiInfo instances
        data = self.model_dump(exclude_none=True, exclude_unset=True)
        if self.ui_infos:
            for etype, ui_info in self.ui_infos.items():
                if isinstance(ui_info, UiInfo):
                    data["ui_infos"][etype] = ui_info.to_dict(lang=lang)
        return data


class EntityCollectionResponse(BaseModel):
    """Response for entity collection"""

    entities: list[Entity]
    next_entity_id: str | None = None
    last_updated: int

    def to_dict(self, lang: str | None = None):
        # apply to_dict on each entity if they are Entity instances
        data = self.model_dump(exclude_none=True, exclude_unset=True)
        if self.entities:
            data["entities"] = [entity.to_dict(lang=lang) for entity in self.entities]
        return data


class URL:
    """URL class for handling URLs."""

    def __init__(self, url: str | HttpUrl):
        self._url = HttpUrl(url)
        self._original = url

    def __str__(self):
        return self._url.__str__()

    def __repr__(self):
        return self.__str__()

    def url(self):
        return self._url

    def __eq__(self, other):
        if isinstance(other, URL):
            return self._url == other.url()
        if isinstance(other, str):
            return self._url == HttpUrl(other)
        if (
            isinstance(other, pydantic_core._pydantic_core.Url)
            or isinstance(other, pydantic_core.Url)
            or isinstance(other, HttpUrl)
        ):
            return self._url == other
        return False

    def __hash__(self):
        return hash(self._url)

    def add_query_params(self, params: dict) -> "URL":
        """Adds query parameters to a URL and returns a new URL.
        :param url: The URL to add the query parameters to.
        :param params: The query parameters to add.
        :return: The URL with the query parameters added.
        """
        url_parts = list(urllib.parse.urlparse(str(self)))
        query = dict(urllib.parse.parse_qsl(url_parts[4]))
        query.update(params)
        # do not urlencode the query parameters, as the URL is used for fetching
        # and the query parameters are already encoded
        url_parts[4] = urllib.parse.urlencode(query, safe=":/")
        return URL(urllib.parse.urlunparse(url_parts))

    def remove_trailing_slashes(self) -> str:
        """Removes trailing slashes from a URL and returns the new URL as a string.
        :param url: The URL to remove the trailing slashes from.
        :return: The URL without trailing slashes as a string
        """
        url_parts = list(urllib.parse.urlparse(str(self)))
        url_parts[2] = url_parts[2].rstrip("/")
        return urllib.parse.urlunparse(url_parts)


def get_payload(jws_str: str) -> dict:
    """Gets the payload of a JWS.

    :param jws_str: The JWS as a string.
    :return: The payload of the JWS as a dictionary.
    """
    jws = factory(jws_str)
    if not jws:
        raise InternalException("Could not parse entity configuration as JWS.")

    payload = jws.jwt.payload()
    if not payload:
        raise InternalException("Could not parse entity configuration payload.")
    if not isinstance(payload, dict):
        try:
            payload = json.loads(payload)
        except ValueError:
            raise InternalException(
                "Entity configuration payload is not a mapping: %s" % payload
            )

    return payload


class EntityStatementPlus(EntityStatement):
    """Entity statement with additional properties."""

    def __init__(self, jwt: str):
        payload = get_payload(jwt)
        super().__init__(**payload)
        self._jwt = jwt
        self._request_timestamp = int(time.time())
        self._ttl = (
            payload.get("exp", 0) - self._request_timestamp
            if "exp" in payload
            else None
        )

    @property
    def request_timestamp(self) -> int:
        return self._request_timestamp

    def get_jwt(self) -> str:
        return self._jwt

    def get_entity_types(self) -> list[EntityType]:
        """Returns the entity types from the entity statement.
        :return: The entity types as a list of strings.
        """
        md = self.get("metadata")
        if not md:
            raise InternalException("No metadata found in entity statement")
        etypes = list(md.to_dict().keys())
        if len(etypes) == 0:
            raise InternalException("Empty metadata")
        return etypes

    def get_entity_type(self) -> EntityType:
        """Returns the entity type from the entity statement.
        :return: The entity type as a string.
        """
        md = self.get("metadata")
        if not md:
            raise InternalException("No metadata found in entity statement")
        etypes = list(md.to_dict().keys())
        if len(etypes) == 0:
            raise InternalException("Empty metadata")
        if len(etypes) > 1:
            logger.warning(
                "Entity has multiple metadata types, choosing one randomly with priority for non-leaf entities."
            )
            if "federation_entity" in etypes:
                return [t for t in etypes if t != "federation_entity"][0]
        return etypes[0]
