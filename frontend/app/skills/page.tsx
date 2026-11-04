"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Section,
  Stat,
  StatRow,
  Table,
  Th,
  Td,
  Tr,
  Button,
  Input,
  Tag,
  Spinner,
  EmptyState,
  Note,
} from "../components/ui";
import { getSkills, addSkill, deleteSkill, Skill } from "../lib/api";
import { X } from "lucide-react";

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [newSkillName, setNewSkillName] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    loadSkills();
  }, []);

  async function loadSkills() {
    try {
      const data = await getSkills();
      setSkills(data);
    } catch {
      setError("Failed to load skills. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  async function handleAddSkill(e: React.FormEvent) {
    e.preventDefault();
    if (!newSkillName.trim()) return;
    setAdding(true);
    setError(null);

    try {
      const newSkill = await addSkill(newSkillName.trim());
      setSkills((prev) => [...prev, newSkill]);
      setNewSkillName("");
    } catch (err: any) {
      setError(err.message || "Failed to add skill.");
    } finally {
      setAdding(false);
    }
  }

  async function handleDeleteSkill(skillId: string, skillName: string) {
    try {
      await deleteSkill(skillId);
      setSkills((prev) => prev.filter((s) => s.id !== skillId));
    } catch (err: any) {
      setError(err.message || `Failed to delete ${skillName}.`);
    }
  }

  const filteredSkills = useMemo(
    () =>
      skills
        .filter((s) =>
          s.name.toLowerCase().includes(searchQuery.toLowerCase())
        )
        .sort((a, b) => a.name.localeCompare(b.name)),
    [skills, searchQuery]
  );

  // Extracted from a resume vs. entered by hand.
  const extractedCount = skills.filter(
    (s) => s.source_resume_id !== null
  ).length;

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl">Skills</h1>
        <p className="mt-1.5 text-sm text-ink-tertiary">
          Your deduplicated inventory — extracted from resumes and curated by
          hand.
        </p>
      </header>

      <StatRow className="md:grid-cols-3">
        <Stat label="Total" value={skills.length} hint="In inventory" />
        <Stat
          label="Extracted"
          value={extractedCount}
          hint="Parsed from resumes"
        />
        <Stat
          label="Added manually"
          value={skills.length - extractedCount}
          hint="Entered by hand"
        />
      </StatRow>

      <Section
        title="Inventory"
        action={
          <Input
            type="search"
            placeholder="Search skills…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-[220px]"
            aria-label="Search skills"
          />
        }
      >
        <form onSubmit={handleAddSkill} className="flex gap-2">
          <Input
            placeholder="Add a skill — e.g. GraphQL, Docker, Figma"
            value={newSkillName}
            onChange={(e) => setNewSkillName(e.target.value)}
            className="max-w-[340px]"
            aria-label="New skill name"
          />
          <Button type="submit" disabled={adding || !newSkillName.trim()}>
            {adding && <Spinner className="h-3.5 w-3.5" />}
            Add
          </Button>
        </form>

        {error && <Note variant="bad">{error}</Note>}

        {filteredSkills.length === 0 ? (
          <EmptyState
            title={searchQuery ? "No matches" : "No skills yet"}
            description={
              searchQuery
                ? `Nothing in the inventory matches “${searchQuery}”.`
                : "Upload a resume to extract skills automatically, or add one above."
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Skill</Th>
                <Th className="w-[130px]">Source</Th>
                <Th className="w-[110px] text-right">Confidence</Th>
                <Th className="w-[60px] text-right">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {filteredSkills.map((skill) => (
                <Tr key={skill.id}>
                  <Td className="text-ink">{skill.name}</Td>
                  <Td>
                    <Tag
                      variant={
                        skill.source_resume_id ? "accent" : "default"
                      }
                    >
                      {skill.source_resume_id ? "Extracted" : "Manual"}
                    </Tag>
                  </Td>
                  <Td className="text-right">
                    {skill.confidence ? (
                      <span data-numeric>
                        {Math.round(skill.confidence * 100)}%
                      </span>
                    ) : (
                      <span className="text-rule-strong">—</span>
                    )}
                  </Td>
                  <Td className="text-right">
                    <button
                      type="button"
                      onClick={() => handleDeleteSkill(skill.id, skill.name)}
                      title={`Remove ${skill.name}`}
                      className="rounded p-1 text-ink-tertiary opacity-0 transition-colors hover:bg-sunken hover:text-bad focus-visible:opacity-100 group-hover:opacity-100"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Section>
    </div>
  );
}
