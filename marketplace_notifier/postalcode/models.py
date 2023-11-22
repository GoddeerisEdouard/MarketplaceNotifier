import json
import re
import urllib.parse
from abc import ABC, abstractmethod
from typing import Optional, List, ClassVar

import aiohttp
import pydantic
from pydantic import BaseModel, Field, field_validator

from marketplace_notifier.utils.api_utils import get_request_response

BELGIAN_POSTAL_CODE_REGEX = "^[1-9]{1}[0-9]{3}$"
BELGIAN_CITY_REGEX = "^[A-Za-zÀ-ÿ\\.'*`´’,\\- \"]{1,34}$"

BelgianCityType = pydantic.constr(pattern=BELGIAN_CITY_REGEX)


class ILocationFilter(BaseModel, ABC):
    """
    class representing parsed location filters
    """
    RADIUS_LIST: ClassVar[List[Optional[int]]]
    city: BelgianCityType = Field(..., description="Valid belgian city name")
    postal_code: int = Field(..., description="Valid belgian postal code")
    radius: int


    @classmethod
    async def get_valid_postal_code_and_city(cls, client_session: aiohttp.ClientSession,
                                             postal_code_or_city: str) -> Optional[dict]:
        """
        helper method to get the postal code of a given city or the city of a given postal code
        city can be either in French or Dutch
        :param client_session: used to make the GET request for the postal code data
        :param postal_code_or_city: a postal code or a city (Dutch or French)
        :return: None if invalid postal_code_or_city, else a dict of  the postal code with its matching city in Dutch
        """

        postal_code_or_city_normalized = str(postal_code_or_city).lower()
        # prevent GET requests for invalid postal code / city
        if not re.match(f"{BELGIAN_CITY_REGEX}|{BELGIAN_POSTAL_CODE_REGEX}", postal_code_or_city_normalized):
            return

        api_url = f"https://opzoeken-postcode.be/{urllib.parse.quote_plus(postal_code_or_city_normalized)}.json"
        response = await get_request_response(client_session, api_url)
        response_json = json.loads(response)
        if response_json:
            for postal_code_and_city_model in response_json:
                postal_code_and_city_model_obj = PostalCodeAPIResponseModel.model_validate(
                    postal_code_and_city_model["Postcode"])

                # check if any postal code or city matches the given postal code, if it does, return that element
                if postal_code_and_city_model_obj.postcode_hoofdgemeente == postal_code_or_city_normalized \
                        or postal_code_and_city_model_obj.postcode_deelgemeente == postal_code_or_city_normalized:
                    return {"postal_code": int(postal_code_and_city_model_obj.postcode_hoofdgemeente),
                            "city": postal_code_and_city_model_obj.naam_hoofdgemeente.capitalize()}

                elif postal_code_and_city_model_obj.naam_hoofdgemeente == postal_code_or_city_normalized \
                        or postal_code_and_city_model_obj.naam_deelgemeente == postal_code_or_city_normalized:
                    return {"postal_code": int(postal_code_and_city_model_obj.postcode_hoofdgemeente),
                            "city": postal_code_and_city_model_obj.naam_hoofdgemeente.capitalize()}

    @field_validator("radius")
    def distance_converter(cls, v: int) -> int:
        """
        only allow tweedehands / 2ememain 's GUI distance input values and convert to closest match
        """
        if not cls.RADIUS_LIST:
            return v

        return cls.RADIUS_LIST[min(range(len(cls.RADIUS_LIST)), key=lambda i: abs(cls.RADIUS_LIST[i] - v))]

    @field_validator("postal_code")
    def belgian_postal_code_validation(cls, v: int) -> int:
        if not re.match(BELGIAN_POSTAL_CODE_REGEX, str(v)):
            raise ValueError(f"{v} is not a valid belgian postal code")
        return v


# Postalcode API related

class PostalCodeAPIResponseModel(BaseModel):
    postcode_hoofdgemeente: str
    naam_hoofdgemeente: str
    postcode_deelgemeente: str
    naam_deelgemeente: str
    taal: str
    region: str
    longitude: str
    latitude: str

    class Config:
        str_to_lower = True
