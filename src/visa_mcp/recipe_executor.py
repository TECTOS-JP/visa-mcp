"""
Recipe 実行エンジン (v0.3.0)

YAML の recipes セクションに定義された複数コマンドのシーケンスを
パラメータ展開 + 安全制約検証 + 順次送信して実行する。
"""
from __future__ import annotations
import logging
from typing import Any

from .models.instrument_def import InstrumentDefinition, RecipeDefinition
from .utils.expression import resolve_arg, ExpressionError
from .utils.param_validator import validate_and_build_scpi, ParameterValidationError
from .visa_manager import VisaManager, VisaError
from .session_manager import InstrumentSession
from . import safety as sf

logger = logging.getLogger(__name__)


async def execute_recipe(
    visa: VisaManager,
    session: InstrumentSession,
    recipe_name: str,
    parameters: dict[str, Any] | None,
    override_safety: bool = False,
    override_reason: str = "",
) -> dict:
    """
    指定の recipe を実行する。

    返り値: 各ステップの実行結果を含む辞書
    """
    parameters = parameters or {}

    if session.definition is None:
        return {
            "success": False,
            "error": "NoDefinitionFound",
            "message": "機器定義が読み込まれていません",
        }

    recipe: RecipeDefinition | None = session.definition.recipes.get(recipe_name)
    if recipe is None:
        return {
            "success": False,
            "error": "RecipeNotFound",
            "message": f"recipe '{recipe_name}' は定義されていません",
            "available_recipes": list(session.definition.recipes.keys()),
        }

    # パラメータ検証 (簡易: 必須チェックのみ)
    for p in recipe.parameters:
        if p.required and p.name not in parameters and p.default is None:
            return {
                "success": False,
                "error": "MissingParameter",
                "message": f"必須パラメータ '{p.name}' が指定されていません",
            }
    # default 適用
    variables = dict(parameters)
    for p in recipe.parameters:
        if p.name not in variables and p.default is not None:
            variables[p.name] = p.default

    step_results: list[dict] = []
    conn = session.definition.connection
    mode = sf.get_safety_mode()

    for idx, step in enumerate(recipe.steps):
        step_label = f"step {idx+1}: {step.command}"
        cmd_def = session.definition.commands.get(step.command)
        if cmd_def is None:
            step_results.append({
                "step": idx, "command": step.command,
                "success": False, "error": "CommandNotFound",
                "message": f"コマンド '{step.command}' が定義されていません",
            })
            return {"success": False, "recipe": recipe_name, "steps_executed": step_results}

        # 引数の式展開
        try:
            resolved_args = {k: resolve_arg(v, variables) for k, v in step.args.items()}
        except ExpressionError as e:
            step_results.append({
                "step": idx, "command": step.command,
                "success": False, "error": "ExpressionError",
                "message": str(e),
            })
            return {"success": False, "recipe": recipe_name, "steps_executed": step_results}

        # 安全制約検証
        violations = sf.validate(
            session.definition, step.command, resolved_args,
            session_history=session.command_history,
        )
        action, msg = sf.decide_action(violations, mode, override_safety, override_reason or None)

        if action in ("block_advisory", "block_strict"):
            sf.write_audit(
                session.resource_name, step.command, resolved_args, violations,
                action=action, mode=mode,
                override_safety=override_safety, override_reason=override_reason or None,
            )
            step_results.append({
                "step": idx, "command": step.command,
                "success": False, "blocked_by_safety": True,
                "violations": list(violations), "action": action,
                "message": msg,
            })
            return {
                "success": False, "recipe": recipe_name,
                "steps_executed": step_results,
                "halted_at_step": idx,
            }

        if violations:
            sf.write_audit(
                session.resource_name, step.command, resolved_args, violations,
                action="proceed_with_override" if override_safety else "proceed_permissive",
                mode=mode,
                override_safety=override_safety, override_reason=override_reason or None,
            )

        # パラメータ検証 + SCPI 組み立て
        try:
            scpi = validate_and_build_scpi(cmd_def, resolved_args)
        except ParameterValidationError as e:
            step_results.append({
                "step": idx, "command": step.command,
                "success": False, "error": "ParameterValidationError",
                "message": str(e),
            })
            return {"success": False, "recipe": recipe_name, "steps_executed": step_results}

        timeout_ms = cmd_def.timeout_ms or conn.default_timeout_ms

        # 送信
        try:
            if cmd_def.type == "query":
                raw = await visa.query(
                    session.resource_name, scpi, timeout_ms=timeout_ms,
                    read_termination=conn.read_termination,
                    write_termination=conn.write_termination,
                )
                step_results.append({
                    "step": idx, "command": step.command,
                    "args": resolved_args, "scpi_sent": scpi,
                    "raw_response": raw,
                    "success": True,
                })
            else:
                await visa.write(
                    session.resource_name, scpi, timeout_ms=timeout_ms,
                    read_termination=conn.read_termination,
                    write_termination=conn.write_termination,
                )
                step_results.append({
                    "step": idx, "command": step.command,
                    "args": resolved_args, "scpi_sent": scpi,
                    "success": True,
                })
            session.record_command(step.command)
        except VisaError as e:
            step_results.append({
                "step": idx, "command": step.command,
                "success": False, "error": type(e).__name__,
                "message": str(e),
            })
            return {"success": False, "recipe": recipe_name, "steps_executed": step_results}

    return {
        "success": True,
        "recipe": recipe_name,
        "steps_executed": step_results,
        "step_count": len(step_results),
    }
