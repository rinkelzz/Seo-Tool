"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, ApiError } from "@/lib/api";

export async function createProjectAction(
  _prevState: { error?: string } | undefined,
  formData: FormData,
): Promise<{ error?: string }> {
  const name = String(formData.get("name") ?? "").trim();
  const domain = String(formData.get("domain") ?? "").trim();
  const baseUrl = String(formData.get("base_url") ?? "").trim();
  const robotsRespect = formData.get("robots_respect") === "on";
  const jsRender = formData.get("js_render") === "on";
  const scheduleRaw = String(formData.get("schedule_interval_minutes") ?? "").trim();
  const scheduleInterval = scheduleRaw === "" || scheduleRaw === "0" ? null : Number(scheduleRaw);

  if (!name || !domain || !baseUrl) {
    return { error: "Name, Domain und Base-URL sind erforderlich." };
  }
  if (scheduleInterval !== null && (!Number.isFinite(scheduleInterval) || scheduleInterval < 15)) {
    return { error: "Crawl-Plan: bitte ein Intervall von mindestens 15 Minuten wählen." };
  }

  let project;
  try {
    project = await api.createProject({
      name,
      domain,
      base_url: baseUrl,
      robots_respect: robotsRespect,
      js_render: jsRender,
      schedule_interval_minutes: scheduleInterval,
    });
  } catch (err) {
    if (err instanceof ApiError) {
      return { error: `Backend lehnte ab: ${err.message}` };
    }
    return { error: `Unerwarteter Fehler: ${(err as Error).message}` };
  }

  revalidatePath("/");
  redirect(`/projects/${project.id}`);
}

export async function triggerCrawlAction(formData: FormData): Promise<void> {
  const projectId = Number(formData.get("project_id"));
  if (!Number.isFinite(projectId)) {
    throw new Error("project_id missing or invalid");
  }
  await api.triggerCrawl(projectId);
  revalidatePath(`/projects/${projectId}`);
}
