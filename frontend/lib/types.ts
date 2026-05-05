export type ChoiceOption = {
  key: string;
  label: string;
};

export type ApiResponse = {
  session_id: string;
  status: string;
  assistant_message: string;
  input_mode: "text" | "choices" | "contact" | "done";
  choices: ChoiceOption[];
  progress: {
    label: string;
    current: number;
    total: number;
  };
  meta: Record<string, unknown> & {
    result_unlocked?: boolean;
    final_offer?: boolean;
    result_ready?: boolean;
  };
};

export type Message = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

export type SessionState = {
  session_id: string;
  status: string;
  current_stage: string;
  dream?: string | null;
  user_name?: string | null;
  user_age?: number | null;
  contact_name?: string | null;
  phone_number?: string | null;
  phone_verified: boolean;
  result_unlocked: boolean;
  progress: {
    label: string;
    current: number;
    total: number;
  };
  state: Record<string, unknown>;
  result: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ContactCodeResponse = {
  session_id: string;
  contact_name: string;
  phone_number: string;
  provider: string;
  expires_at: string;
  dev_mode: boolean;
  dev_code?: string | null;
};

export type ContactVerifyResponse = {
  session_id: string;
  access_token: string;
  response: ApiResponse;
};

export type AdminFilter =
  | "all"
  | "with_phone"
  | "verified"
  | "unlocked"
  | "with_phone_unverified"
  | "verified_locked";
export type AdminPeriod = "today" | "7d" | "30d" | "custom";

export type AdminSessionSummary = {
  session_id: string;
  created_at: string;
  last_activity_at: string;
  display_name?: string | null;
  phone_number?: string | null;
  current_stage: string;
  status_label: string;
  stopped_at_label: string;
  status: string;
  phone_verified: boolean;
  result_unlocked: boolean;
  bonus_downloaded: boolean;
  blueprint_downloaded: boolean;
  top_shadow_names: string[];
  user_age?: number | null;
  dream?: string | null;
  passport_title?: string | null;
  behavior_shadow_name?: string | null;
  personality_shadow_name?: string | null;
  root_shadow_name?: string | null;
  link_key?: string | null;
};

export type AdminSessionListResponse = {
  filter: AdminFilter;
  total_count: number;
  items: AdminSessionSummary[];
  analytics: {
    total_sessions?: number;
    completed_sessions?: number;
    reached_passport?: number;
    passport_conversion_percent?: number;
    top_passports?: [string, number][];
    top_behavior_shadows?: [string, number][];
    top_personality_shadows?: [string, number][];
    top_root_shadows?: [string, number][];
    top_routes?: [string, number][];
  };
};

export type AdminSessionDetail = {
  session_id: string;
  created_at: string;
  last_activity_at: string;
  updated_at: string;
  completed_at?: string | null;
  display_name?: string | null;
  phone_number?: string | null;
  current_stage: string;
  status_label: string;
  stopped_at_label: string;
  status: string;
  dream?: string | null;
  user_age?: number | null;
  user_goal_text?: string | null;
  phone_verified: boolean;
  phone_verified_at?: string | null;
  result_unlocked: boolean;
  result_released_at?: string | null;
  bonus_downloaded: boolean;
  blueprint_downloaded: boolean;
  top_shadow_names: string[];
  client_text?: string | null;
  internal_addendum?: string | null;
  result_summary?: string | null;
  mechanism_formula?: string | null;
  manifestation?: string | null;
  price?: string | null;
  hidden_resource?: string | null;
  screen_phrase?: string | null;
  micro_permission?: string | null;
  session_state: Record<string, unknown>;
  v1_2: Record<string, unknown>;
};
