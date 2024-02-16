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
    changed: str | typing.Literal[False] | None = dc.field(default=None, init=False)
    modified: str | None = dc.field(default=None, init=False)
    name: str

    def changed_from(self, expected: "Entry"):
        if self.type != expected.type:
            return f"was_{expected.type}"
        if (self.modified is not None and expected.modified is not None) and self.modified != expected.modified:
            return "modified"
        return False

DirectoryContent = dict[str, Entry]

@dc.dataclass
class FileEntry(Entry):
    size: int | None = None
    sha256: str | None = None

    def __post_init__(self):
        self.type = "file"

    def changed_from(self, expected: "FileEntry"):
        changed = super().changed_from(expected)
        if changed: return changed
        if (self.size is not None and expected.size is not None) and self.size != expected.size:
            return "modified"
        if (self.sha256 is not None and expected.sha256 is not None) and self.sha256 != expected.sha256:
            return "modified"
        return False


@dc.dataclass
class DirectoryEntry(Entry):
    content: DirectoryContent = dc.field(default_factory=dict)

    def __post_init__(self):
        self.type = "dir"

    def changed_from(self, expected: "FileEntry"):
        return super().changed_from(expected)

def merge_entries(actual: DirectoryContent, expected: DirectoryContent) -> DirectoryContent:
    result: DirectoryContent = {}
    for entry in actual.values():
        expected_entry = expected.get(entry.name, None)
        result_entry = dc.replace(entry)
        if isinstance(result_entry, FileEntry) and isinstance(expected_entry, FileEntry):
            result_entry.sha256 = expected_entry.sha256
        if expected_entry is None:
            result_entry.changed = "added"
        else:
            result_entry.changed = entry.changed_from(expected_entry)
        expected_content = {} if not isinstance(expected_entry, DirectoryEntry) else expected_entry.content
        if isinstance(result_entry, DirectoryEntry):
            result_entry.content = merge_entries(result_entry.content, expected_content)
        result[entry.name] = result_entry

    return result



def recursive_change(entry: Entry, changed: str | typing.Literal[False]) -> Entry:
    if isinstance(entry, DirectoryEntry):
        changed_entry = dc.replace(entry)
        changed_entry.content = {}
        for sub_entry in entry.content.values():
            changed_entry.content[sub_entry.name] = recursive_change(sub_entry, changed)
    else:
        changed_entry = dc.replace(entry)
    changed_entry.changed = changed
    return changed_entry


def create_update_list(wanted: DirectoryContent, actual: DirectoryContent) -> tuple[DirectoryContent, DirectoryContent]:
    to_remove = DirectoryContent()
    to_add = DirectoryContent()

    def with_changed(entry: Entry, changed: str | typing.Literal[False]):
        entry.changed = changed
        return entry

    for entry in actual.values():
        wanted_entry = wanted.get(entry.name, None)
        if wanted_entry is None or entry.changed or wanted_entry.changed_from(entry):
            to_remove[entry.name] = recursive_change(entry, "remove")

    for entry in wanted.values():
        entry_to_add = dc.replace(entry)
        actual_entry = actual.get(entry.name, None)
        if actual_entry is None or actual_entry.changed or entry.changed_from(actual_entry):
            to_add[entry.name] = recursive_change(entry_to_add, "add")
        elif isinstance(entry, DirectoryEntry):
            actual_content = {} if not isinstance(actual_entry, DirectoryEntry) else actual_entry.content
            sub_remove, sub_add = create_update_list(entry.content, actual_content)
            if len(sub_remove) != 0:
                to_remove[entry.name] = with_changed(dc.replace(entry_to_add, content=sub_remove), False)
            if len(sub_add) != 0:
                to_add[entry.name] = with_changed(dc.replace(entry_to_add, content=sub_add), False)

    return to_remove, to_add

def merge_modified(file_list: DirectoryContent, file_dates: DirectoryContent) -> DirectoryContent:
    result = DirectoryContent()
    for entry in file_list.values():
        dated_entry = file_dates.get(entry.name, None)
        result_entry = dc.replace(entry)
        dated_content = {} if not isinstance(dated_entry, DirectoryEntry) else dated_entry.content
        if dated_entry is not None:
            result_entry.modified = dated_entry.modified
        if isinstance(result_entry, DirectoryEntry):
            result_entry.content = merge_modified(result_entry.content, dated_content)
        result[entry.name] = result_entry
    return result
