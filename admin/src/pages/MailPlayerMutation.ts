import { useRef } from "react"
import { message } from "antd"
import { useMutation, type UseMutationOptions } from "@tanstack/react-query"

/** Keep rapid repeated clicks from starting another write before React renders loading. */
export function useMailPlayerMutation<TData = unknown, TVariables = void>(
    options: UseMutationOptions<TData, Error, TVariables>,
) {
    const busy = useRef(false)
    const mutation = useMutation({
        ...options,
        onError: options.onError ?? ((error: Error) => { void message.error(error.message) }),
        onSettled: async (...args) => {
            try {
                await options.onSettled?.(...args)
            } finally {
                busy.current = false
            }
        },
    })
    const start = () => {
        if (busy.current) {
            message.info("操作正在进行，请等待结果")
            return false
        }
        busy.current = true
        return true
    }
    return {
        ...mutation,
        mutate: (...args: Parameters<typeof mutation.mutate>) => {
            if (start()) mutation.mutate(...args)
        },
        mutateAsync: (...args: Parameters<typeof mutation.mutateAsync>) => {
            if (!start()) return Promise.reject(new Error("操作正在进行，请等待结果"))
            return mutation.mutateAsync(...args)
        },
    }
}
