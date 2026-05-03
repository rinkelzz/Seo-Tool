"use client";

import Link from "next/link";
import { useFormState, useFormStatus } from "react-dom";

import { createProjectAction } from "@/app/actions";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";

const initialState: { error?: string } = {};

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? "Wird erstellt…" : "Projekt anlegen"}
    </Button>
  );
}

export default function NewProjectPage() {
  const [state, formAction] = useFormState(createProjectAction, initialState);

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-2xl font-semibold">Neues Projekt</h1>

      <Card>
        <CardHeader>
          <CardTitle>Stammdaten</CardTitle>
        </CardHeader>
        <CardContent>
          <form action={formAction} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Anzeigename</Label>
              <Input id="name" name="name" placeholder="Mein Webshop" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="domain">Domain</Label>
              <Input id="domain" name="domain" placeholder="example.com" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="base_url">Base-URL</Label>
              <Input
                id="base_url"
                name="base_url"
                type="url"
                placeholder="https://example.com/"
                required
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                id="robots_respect"
                name="robots_respect"
                type="checkbox"
                defaultChecked
                className="h-4 w-4 rounded border-slate-300"
              />
              <Label htmlFor="robots_respect">robots.txt respektieren</Label>
            </div>
            <div className="flex items-center gap-2">
              <input
                id="js_render"
                name="js_render"
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300"
              />
              <Label htmlFor="js_render">JavaScript-Rendering (Phase 1B)</Label>
            </div>

            {state?.error && (
              <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{state.error}</p>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <Link href="/">
                <Button type="button" variant="secondary">
                  Abbrechen
                </Button>
              </Link>
              <SubmitButton />
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
