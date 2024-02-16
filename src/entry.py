import json
import dataclasses as dc
import types
import typing
import typeguard


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dc.is_dataclass(o):
            return dc.asdict(
                o, dict_factory=lambda x: {k: v for (k, v) in x if v is not None}
            )
        return super().default(o)


def check_type(val, expected_type):
    if isinstance(expected_type, str):
        expected_type = eval(expected_type)
    if typing.get_origin(expected_type) is types.UnionType:
        expected_type = typing.get_args(expected_type)
    if typing.get_origin(expected_type) is None:
        return isinstance(val, expected_type)
    else:
        try:
            typeguard.check_type(val, expected_type)
            return True
        except typeguard.TypeCheckError:
            return False

class EntryJSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)
    def object_hook(self, obj: dict):
        if 'type' in obj:
            if obj["type"] == "file":
                cls_type = FileEntry
            elif obj["type"] == "dir":
                cls_type = DirectoryEntry
            else:
                cls_type = None
            if cls_type is not None:
                cls_fields: typing.Tuple[dc.Field, ...] = dc.fields(cls_type)
                init_dict = {}
                after_dict = {}
                for x in cls_fields:
                    required = not (x.default != dc._MISSING_TYPE and x.default_factory != dc._MISSING_TYPE)
                    has_val = x.name in obj
                    if has_val:
                        val = obj[x.name]
                        if not check_type(val, x.type):
                            raise RuntimeError(f"Type of {x.name} ({type(obj[x.name])}) does not match requirement {x.type}")
                                
                    if x.init:
                        if has_val:
                            init_dict[x.name] = val
                        elif required:
                            raise RuntimeError(f"Missing required field {x.name} for {cls_type}")
                    elif has_val:
                        after_dict[x.name] = val
                result = cls_type(**init_dict)
                for field in after_dict:
                    setattr(result, field, after_dict[field])
                return result
        return obj


@dc.dataclass
class Entry:
    type: str = dc.field(init=False)
    changed: str | None = dc.field(default=None, init=False)
    modified: str | None = dc.field(default=None, init=False)


@dc.dataclass
class FileEntry(Entry):
    name: str
    size: int | None = None
    sha256: str | None = None

    def __post_init__(self):
        self.type = "file"


@dc.dataclass
class DirectoryEntry(Entry):
    name: str
    content: dict[str, Entry] = dc.field(default_factory=dict)

    def __post_init__(self):
        self.type = "dir"
