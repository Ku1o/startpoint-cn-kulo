import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"

/** This exact extension contains only the five reviewed iOS texture/atlas files.
 * It changes the download chain, not the original quest/shop definitions or an
 * existing deployment receipt. Unknown manifests retain their own identity.
 * Both pins are required; a filename or a claimed image-only flag is not proof.
 */
const iosResourceExtension = {
    manifestSha256: "8050a95d1e4baf30cc3f98573498f46e993210b60bdff62ed36dd1c8157fe995",
    archive: "assets/asset-patch/active/pinball-1.4.350-1.4.351-1-ios-resource-closure.zip",
    archiveBytes: 552471,
    archiveSha256: "2be5708ff19fd68088e2d97fbb13900e8e87e20157a7192e5b9b770db2ceb02c",
    contentSource: { assetVersion: "1.4.350", manifestSha256: "4cb3dd337ac062af6845591b85cf27d3bc203160923f74c2cf1c7a2883b76843" },
} as const
const sha = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex")

export function readContentResourceSourceSync(root = path.resolve(__dirname, "../..")): {
    assetVersion: string; manifestSha256: string
} {
    const bytes = readFileSync(path.join(root, "assets/asset-patch/manifest.json")), manifestSha256 = sha(bytes)
    if (manifestSha256 !== iosResourceExtension.manifestSha256) {
        return { assetVersion: JSON.parse(bytes.toString("utf8")).cdn_version, manifestSha256 }
    }
    const archive = readFileSync(path.join(root, iosResourceExtension.archive))
    if (archive.length !== iosResourceExtension.archiveBytes || sha(archive) !== iosResourceExtension.archiveSha256) {
        throw new Error("Reviewed iOS resource extension archive identity mismatch")
    }
    return { ...iosResourceExtension.contentSource }
}
