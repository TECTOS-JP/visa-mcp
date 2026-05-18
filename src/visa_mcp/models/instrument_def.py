from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field


class ParameterDefinition(BaseModel):
    name: str
    description: str = ""
    type: Literal["integer", "float", "string", "enum"] = "string"
    required: bool = True
    range: list[float] | None = None       # integer/float 用 [min, max]
    choices: list[str] | None = None       # enum 用
    default: Any = None


class ReturnDefinition(BaseModel):
    type: Literal["none", "integer", "float", "boolean", "string"] = "string"
    unit: str = ""
    description: str = ""


class CommandDefinition(BaseModel):
    scpi: str
    type: Literal["query", "write"] = "query"
    description: str = ""
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    returns: ReturnDefinition = Field(default_factory=ReturnDefinition)
    timeout_ms: int | None = None          # 省略時は connection.default_timeout_ms を使用


class IdentificationConfig(BaseModel):
    manufacturer_match: str = ""           # 大文字・部分一致
    model_regex: str = ""                  # 正規表現


class SerialConfig(BaseModel):
    baud_rate: int = 9600
    data_bits: int = 8
    parity: Literal["N", "E", "O"] = "N"
    stop_bits: float = 1
    flow_control: Literal["none", "xon_xoff", "rts_cts"] = "none"


class ConnectionConfig(BaseModel):
    default_timeout_ms: int = 5000
    read_termination: str = "\n"
    write_termination: str = "\n"
    serial: SerialConfig = Field(default_factory=SerialConfig)


class MetadataConfig(BaseModel):
    manufacturer: str
    model: str
    description: str = ""
    manual_ref: str = ""


class InstrumentDefinition(BaseModel):
    metadata: MetadataConfig
    identification: IdentificationConfig = Field(default_factory=IdentificationConfig)
    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    commands: dict[str, CommandDefinition] = Field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return f"{self.metadata.manufacturer} {self.metadata.model}"
