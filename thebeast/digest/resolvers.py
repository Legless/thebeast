import regex as re  # type: ignore
from typing import Optional, List, Dict, Union, Any, Callable

from jinja2 import Environment, BaseLoader, select_autoescape
from followthemoney.schema import Schema  # type: ignore

from .utils import generate_pseudo_id, jmespath_results_as_array, resolve_callable

# TODO: expose jmespath to templates as a filter?
jinja_env = Environment(loader=BaseLoader(), autoescape=select_autoescape())


def _resolve_literal(
    command_config: str, record: Optional[Union[List, Dict]], values: List[str], entity: Optional[Schema]
) -> List[str]:
    """
    `literal` is simply a string or number constant used for FTM entity field
    """
    return values + [command_config]


def _resolve_entity(
    command_config: str, record: Optional[Union[List, Dict]], values: List[str], entity: Optional[Schema]
) -> List[str]:
    """
    `entity` is a named reference to another entity available in the current context
    i.e as a constant entity or entity of the current collection and its parents
    For now we just adding the reference to the another entity and we'll resolve it later
    TODO: green/red validate if the property allows to reference to another entity
    i.e entity.schema.properties[property_name].type == entity
    TODO: we probably want to preserve the list of property names to resolve later on

    To fool the FTM we supply something that looks like entity ID which we can resolve later
    """
    return values + [generate_pseudo_id(command_config)]


def _resolve_column(
    command_config: str, record: Union[List, Dict], values: List[str], entity: Optional[Schema]
) -> List[str]:
    """
    `column` is a jmespath applied at the current level of the doc
    to collect all the needed values for the field from it
    """

    return values + jmespath_results_as_array(command_config, record)


def _resolve_regex_split(
    command_config: str, record: Union[List, Dict], values: List[str], entity: Optional[Schema]
) -> List[str]:
    """
    `regex_split` is an optional regex splitter to extract multiple
    values for the entity field from the single string.
    """
    new_property_values: List[str] = []

    for property_value in values:
        new_property_values += re.split(command_config, str(property_value), flags=re.V1)

    return new_property_values


def _resolve_regex(
    command_config: str, record: Union[List, Dict], values: List[str], entity: Optional[Schema]
) -> List[str]:
    """
    `regex` is an optional regex **matcher** to match the part of the extracted string
    and set it as a value for the entity field. It is being applied after the (optional)
    regex_split
    """

    extracted_property_values: List[Any] = []

    for property_value in values:
        if not property_value:
            continue

        m = re.search(command_config, str(property_value), flags=re.V1)
        if m:
            if m.groups():
                # We support both, groups
                extracted_property_values.append(m.group(1))
            else:
                # And full match
                extracted_property_values.append(m.group(0))

    return extracted_property_values


def _resolve_transformer(
    command_config: str, record: Union[List, Dict], values: List[str], entity: Optional[Schema]
) -> List[str]:
    """
    `transformer` is a python function which (currently) accepts only a list of values
    applies some transform to it and returns the modified list. That list will be
    added to the entity instead of the original values
    """

    return resolve_callable(command_config)(values)


def _resolve_augmentor(
    command_config: str, record: Union[List, Dict], values: List[str], entity: Optional[Schema]
) -> List[str]:
    """
    `augmentor` is a similar concept to the `transformer`, but modified list is added
    to the original values
    """

    return values + resolve_callable(command_config)(values)


def _resolve_template(command_config: str, record: Union[List, Dict], values: List[str], entity: Schema) -> List[str]:
    """
    `template` is a jinja template str that will be rendered using the context
    which contains current half-finished entity and original
    """
    template = jinja_env.from_string(command_config)
    return values + [template.render(entity=entity.properties, record=record)]


def _resolve_configs(property_configs: List, commands_mapping: Dict[str, Callable], **kwargs) -> List[str]:
    """
    A general function that applies all the command from the config to the kwargs
    """

    property_values: List[str] = []

    for property_config in property_configs:
        for command, command_config in property_config.items():
            if command in commands_mapping:
                property_values = commands_mapping[command](
                    command_config=command_config, values=property_values, **kwargs
                )
            else:
                pass
                # TODO: signal to show our disrespect?

    return property_values


def resolve_entity(property_configs: List, record: Union[List, Dict], entity: Schema) -> List[str]:
    """
    A wrapper for _resolve_configs for the entity (all commands are supported)
    """

    return _resolve_configs(
        property_configs=property_configs,
        commands_mapping={
            "literal": _resolve_literal,
            "entity": _resolve_entity,
            "column": _resolve_column,
            "regex_split": _resolve_regex_split,
            "regex": _resolve_regex,
            "transformer": _resolve_transformer,
            "augmentor": _resolve_augmentor,
            "template": _resolve_template,
        },
        record=record,
        entity=entity,
    )


def resolve_constant_statement_meta(property_configs: List) -> List[str]:
    return _resolve_configs(
        property_configs=property_configs,
        commands_mapping={
            "literal": _resolve_literal,
        },
        record=None,
        entity=None,
    )