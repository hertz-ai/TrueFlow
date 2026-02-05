//! TrueFlow Procedural Macros
//!
//! Provides compile-time instrumentation for Rust functions.
//!
//! # Usage
//!
//! ```rust
//! use trueflow_macros::trace;
//!
//! #[trace]
//! fn my_function() {
//!     // Function body is automatically instrumented
//! }
//! ```

use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, ItemFn, ItemMod, visit_mut::VisitMut};

/// Instruments a single function with TrueFlow tracing.
///
/// Wraps the function body in a guard that emits call/return events
/// to the TrueFlow IDE plugin.
///
/// # Example
///
/// ```rust
/// use trueflow_macros::trace;
///
/// #[trace]
/// fn process_data(data: Vec<u8>) -> Result<(), Error> {
///     // Automatically traced
///     validate(&data)?;
///     transform(data)
/// }
/// ```
#[proc_macro_attribute]
pub fn trace(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let input = parse_macro_input!(item as ItemFn);

    let vis = &input.vis;
    let sig = &input.sig;
    let block = &input.block;
    let attrs = &input.attrs;
    let fn_name = &sig.ident;

    // Handle async functions
    let is_async = sig.asyncness.is_some();

    let expanded = if is_async {
        quote! {
            #(#attrs)*
            #vis #sig {
                let _guard = ::trueflow_runtime::enter(
                    module_path!(),
                    stringify!(#fn_name),
                    line!(),
                    file!()
                );
                async move {
                    let result = async #block.await;
                    drop(_guard);
                    result
                }.await
            }
        }
    } else {
        quote! {
            #(#attrs)*
            #vis #sig {
                let _guard = ::trueflow_runtime::enter(
                    module_path!(),
                    stringify!(#fn_name),
                    line!(),
                    file!()
                );
                let result = (|| #block)();
                drop(_guard);
                result
            }
        }
    };

    TokenStream::from(expanded)
}

/// Instruments all functions in a module with TrueFlow tracing.
///
/// Applies the `#[trace]` attribute to all function definitions
/// within the module.
///
/// # Example
///
/// ```rust
/// use trueflow_macros::trace_module;
///
/// #[trace_module]
/// mod my_handlers {
///     pub fn handle_get() { /* traced */ }
///     pub fn handle_post() { /* traced */ }
/// }
/// ```
#[proc_macro_attribute]
pub fn trace_module(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut input = parse_macro_input!(item as ItemMod);

    struct FnInstrumentor;

    impl VisitMut for FnInstrumentor {
        fn visit_item_fn_mut(&mut self, node: &mut syn::ItemFn) {
            // Skip if already has #[trace] or #[no_trace]
            let has_trace_attr = node.attrs.iter().any(|attr| {
                attr.path().is_ident("trace") || attr.path().is_ident("no_trace")
            });

            if !has_trace_attr {
                // Add instrumentation inline (can't add #[trace] from within visit_mut)
                let fn_name = &node.sig.ident;
                let is_async = node.sig.asyncness.is_some();
                let old_block = &node.block;

                let new_block: syn::Block = if is_async {
                    syn::parse_quote! {{
                        let _guard = ::trueflow_runtime::enter(
                            module_path!(),
                            stringify!(#fn_name),
                            line!(),
                            file!()
                        );
                        async move {
                            let result = async #old_block.await;
                            drop(_guard);
                            result
                        }.await
                    }}
                } else {
                    syn::parse_quote! {{
                        let _guard = ::trueflow_runtime::enter(
                            module_path!(),
                            stringify!(#fn_name),
                            line!(),
                            file!()
                        );
                        let result = (|| #old_block)();
                        drop(_guard);
                        result
                    }}
                };

                node.block = Box::new(new_block);
            }

            // Continue visiting nested items
            syn::visit_mut::visit_item_fn_mut(self, node);
        }
    }

    if let Some((_, ref mut items)) = input.content {
        let mut instrumentor = FnInstrumentor;
        for item in items.iter_mut() {
            instrumentor.visit_item_mut(item);
        }
    }

    TokenStream::from(quote! { #input })
}

/// Skips tracing for a function when used within a `#[trace_module]`.
///
/// # Example
///
/// ```rust
/// use trueflow_macros::{trace_module, no_trace};
///
/// #[trace_module]
/// mod handlers {
///     pub fn traced_function() { /* traced */ }
///
///     #[no_trace]
///     pub fn internal_helper() { /* not traced */ }
/// }
/// ```
#[proc_macro_attribute]
pub fn no_trace(_attr: TokenStream, item: TokenStream) -> TokenStream {
    // Just pass through unchanged
    item
}

/// Instruments an impl block, adding tracing to all methods.
///
/// # Example
///
/// ```rust
/// use trueflow_macros::trace_impl;
///
/// struct MyService;
///
/// #[trace_impl]
/// impl MyService {
///     pub fn new() -> Self { MyService }
///     pub fn process(&self, data: &[u8]) { /* traced */ }
/// }
/// ```
#[proc_macro_attribute]
pub fn trace_impl(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut input = parse_macro_input!(item as syn::ItemImpl);

    for item in input.items.iter_mut() {
        if let syn::ImplItem::Fn(method) = item {
            // Skip if already has #[trace] or #[no_trace]
            let has_trace_attr = method.attrs.iter().any(|attr| {
                attr.path().is_ident("trace") || attr.path().is_ident("no_trace")
            });

            if !has_trace_attr {
                let fn_name = &method.sig.ident;
                let is_async = method.sig.asyncness.is_some();
                let old_block = &method.block;

                let new_block: syn::Block = if is_async {
                    syn::parse_quote! {{
                        let _guard = ::trueflow_runtime::enter(
                            module_path!(),
                            stringify!(#fn_name),
                            line!(),
                            file!()
                        );
                        async move {
                            let result = async #old_block.await;
                            drop(_guard);
                            result
                        }.await
                    }}
                } else {
                    syn::parse_quote! {{
                        let _guard = ::trueflow_runtime::enter(
                            module_path!(),
                            stringify!(#fn_name),
                            line!(),
                            file!()
                        );
                        let result = (|| #old_block)();
                        drop(_guard);
                        result
                    }}
                };

                method.block = new_block;
            }
        }
    }

    TokenStream::from(quote! { #input })
}
