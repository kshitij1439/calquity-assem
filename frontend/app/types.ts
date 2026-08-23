export type MaterialType = "matte_clay" | "glossy_plastic" | "brushed_metal" | "glass";
export type EyeExpression = "neutral" | "happy" | "thinking" | "surprised";
export type ActiveAnimation = "float" | "wave" | "bounce" | "idle";

export interface LightingConfig {
  intensity: number;
  direction: "top_left" | "top_right" | "center" | "ambient";
}
